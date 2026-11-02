# 本地交互推理入口：加载权重 → 构造对话模板 → 自回归生成 → 展示回答和生成速度。
import time
import argparse
import random
import warnings
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, TextStreamer
from model.model_minimind import MiniMindConfig, MiniMindForCausalLM
from model.model_lora import *
from trainer.trainer_utils import setup_seed, get_model_params
warnings.filterwarnings('ignore')

# 按参数加载原生 MiniMind 权重或 Transformers 模型，并返回评估模式的模型与分词器。
def init_model(args):
    tokenizer = AutoTokenizer.from_pretrained(args.load_from)
    if 'model' in args.load_from:
        model = MiniMindForCausalLM(MiniMindConfig(
            hidden_size=args.hidden_size,
            num_hidden_layers=args.num_hidden_layers,
            use_moe=bool(args.use_moe),
            inference_rope_scaling=args.inference_rope_scaling
        ))
        moe_suffix = '_moe' if args.use_moe else ''
        ckp = f'./{args.save_dir}/{args.weight}_{args.hidden_size}{moe_suffix}.pth'
        # PyTorch：load_state_dict 按参数/缓冲区名字恢复状态；strict=False 允许缺失/额外键，但不忽略同名张量形状不匹配。
        # PyTorch：load 读取序列化对象；map_location 指定张量加载设备，CPU 加载可避免先占用 GPU 显存。
        model.load_state_dict(torch.load(ckp, map_location=args.device), strict=True)
        if args.lora_weight != 'None':
            apply_lora(model)
            load_lora(model, f'./{args.save_dir}/{args.lora_weight}_{args.hidden_size}.pth')
    else:
        model = AutoModelForCausalLM.from_pretrained(args.load_from, trust_remote_code=True)
    get_model_params(model, model.config)
    return model.half().eval().to(args.device), tokenizer

# 解析运行参数，选择预设问题或交互输入，保留指定条数历史并流式生成回答。
def main():
    parser = argparse.ArgumentParser(description="MiniMind模型推理与对话")
    parser.add_argument('--load_from', default='model', type=str, help="模型加载路径（model=原生torch权重，其他路径=transformers格式）")
    parser.add_argument('--save_dir', default='out', type=str, help="模型权重目录")
    parser.add_argument('--weight', default='full_sft', type=str, help="权重名称前缀（pretrain, full_sft, rlhf, reason, ppo_actor, grpo, spo）")
    parser.add_argument('--lora_weight', default='None', type=str, help="LoRA权重名称（None表示不使用，可选：lora_identity, lora_medical）")
    parser.add_argument('--hidden_size', default=768, type=int, help="隐藏层维度")
    parser.add_argument('--num_hidden_layers', default=8, type=int, help="隐藏层数量")
    parser.add_argument('--use_moe', default=0, type=int, choices=[0, 1], help="是否使用MoE架构（0=否，1=是）")
    parser.add_argument('--inference_rope_scaling', default=False, action='store_true', help="启用RoPE位置编码外推（4倍，仅解决位置编码问题）")
    parser.add_argument('--max_new_tokens', default=8192, type=int, help="最大生成长度（注意：并非模型实际长文本能力）")
    parser.add_argument('--temperature', default=0.85, type=float, help="生成温度，控制随机性（0-1，越大越随机）")
    parser.add_argument('--top_p', default=0.95, type=float, help="nucleus采样阈值（0-1）")
    parser.add_argument('--open_thinking', default=0, type=int, help="是否开启自适应思考（0=否，1=是）")
    parser.add_argument('--historys', default=0, type=int, help="携带历史对话轮数（需为偶数，0表示不携带历史）")
    parser.add_argument('--show_speed', default=1, type=int, help="显示decode速度（tokens/s）")
    parser.add_argument('--device', default='cuda' if torch.cuda.is_available() else 'cpu', type=str, help="运行设备")
    args = parser.parse_args()
    
    prompts = [
        '你有什么特长？',
        '为什么天空是蓝色的',
        '请用Python写一个计算斐波那契数列的函数',
        '解释一下"光合作用"的基本过程',
        '如果明天下雨，我应该如何出门',
        '比较一下猫和狗作为宠物的优缺点',
        '解释什么是机器学习',
        '推荐一些中国的美食'
    ]
    
    conversation = []
    model, tokenizer = init_model(args)
    input_mode = int(input('[0] 自动测试\n[1] 手动输入\n'))
    '''
        TextStreamer 示例：假设用户输入“你好”，模型生成的回答是“你好！我是 MiniMind。”。
        1. tokenizer：把模型输出的 token ID 解码成人能阅读的文字。
        token ID 是词表中的编号，一个 token 不一定对应一个汉字或一个完整单词。
        2. skip_prompt=True：不打印传入 generate 的输入提示（含对话模板和历史对话），
        只打印本次新生成的回答；设为 False 时，输入提示也会被解码打印。
        3. skip_special_tokens=True：作为解码参数传给 tokenizer.decode，
        隐藏分词器登记的特殊 token（例如结束标记），让终端只显示正常文本。
        它只影响显示，不会从生成结果的 token ID 中删除这些标记。

        配合下面的 model.generate(..., streamer=streamer) 使用时，过程可以理解为：
        generate 先把输入提示交给 streamer → 因 skip_prompt=True 而跳过打印；
        随后不断把新生成的 token 交给 streamer → 解码、缓存并逐步打印回答；
        生成结束 → 打印缓存中剩余的文字，并换行。
        终端显示示意（回答是假设的，实际内容由模型生成）：
        💬: 你好
        🧠: 你好！我是 MiniMind。
        其中“💬:”和“🧠:”由本脚本的 print 输出，回答正文由 streamer 逐步输出。
        注意：创建 streamer 本身不会生成或打印回答，必须把它传给 generate。
        流式输出也不保证每收到一个 token 就立即显示一个字，可能会等待完整词片段。
        generate 仍然返回完整的 generated_ids；streamer 不负责保存 response，
        后面仍需切掉输入提示对应的 ID，再 decode 得到用于保存对话历史的回答字符串。
    '''
    streamer = TextStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True) # 流式输出模型回答
    
    '''
        这行用条件表达式选择问题来源：A if 条件 else B 表示条件成立时取 A，否则取 B。
        1. input_mode == 0：取预先定义的 prompts 列表，下面的 for 依次取出每个问题。
        2. 否则：创建一个反复读取键盘输入的迭代器，供下面的 for 使用。
        lambda: input('💬: ') 是一个无参数函数，每次调用才显示提示并等待输入。
        iter(函数, 结束值) 会在每次取下一项时调用函数；返回值等于结束值时停止。
        这里结束值是空字符串 ''，所以直接按回车就结束循环，空字符串不会进入循环体。
        注意：输入几个空格再回车不等于空字符串，仍会作为一个问题处理。
        例如手动模式下：输入“你好”并回车 → prompt 为“你好”，执行一轮模型回答；
        回答结束后再次等待输入；输入“介绍一下自己” → 再回答一轮；直接回车 → 退出。
        创建迭代器时不会立即执行 input，而是在 for 请求下一项时执行。

        【把 iter 拆开理解】
        迭代器就是一个可以不断向它“取下一项”的对象，下面的 for 负责取下一项。
        iter 有两种用法：
            iter(['你好', '你是谁'])：从现成列表中逐项取，列表取完就结束。
            iter(函数, 结束值)：每次调用函数取得新内容，结果等于结束值就结束。
        这里用的是第二种，适合事先不知道用户会输入多少句话的情况。

        先把 lambda 换成普通函数，意思就更容易看清：
            def read_prompt():
                return input('💬: ')

            prompt_iter = iter(read_prompt, '')
            for prompt in prompt_iter:
                print('收到问题：', prompt)

        上面这段示例等价于：
            while True:
                prompt = read_prompt()
                if prompt == '':
                    break
                print('收到问题：', prompt)

        所以 iter(函数, '') 配合 for，完成了“反复调用函数 + 判断是否结束”。
        传入的是 read_prompt，而不是 read_prompt()：前者是函数本身，供以后反复调用；
        后者会立刻执行一次函数，得到输入字符串，不符合这里要求传入可调用对象的用法。
        实际执行顺序：
            for 请求第 1 项 → 调用函数，输入“你好” → prompt = '你好' → 执行循环体。
            for 请求第 2 项 → 再调用函数，输入“你是谁” → prompt = '你是谁' → 执行循环体。
            for 请求第 3 项 → 再调用函数，直接回车 → 得到 '' → for 结束，不进入循环体。
        在本脚本中，循环体负责生成回答：读一句、回答一句，然后才等待下一句。
    '''
    prompt_iter = prompts if input_mode == 0 else iter(lambda: input('💬: '), '')
    for prompt in prompt_iter:
        setup_seed(random.randint(0, 31415926))
        if input_mode == 0: print(f'💬: {prompt}')
        conversation = conversation[-args.historys:] if args.historys else []
        conversation.append({"role": "user", "content": prompt})
        '''
            先把问题整理成模型训练时使用的文本格式，此时 inputs 还是字符串。
            1. 'pretrain' in args.weight：判断权重名称中是否包含子串 'pretrain'。
            例如 pretrain 会进入这个分支，full_sft 会进入 else 分支。
            预训练分支使用“起始标记 + 当前问题”，让模型继续往后续写。
            本项目默认 tokenizer.bos_token 是 '<|im_start|>'；若 prompt 是“你好”，
            拼接后就是 '<|im_start|>你好'。这个分支没有使用 conversation 中的历史。

            【为什么预训练时可以直接用 tokenizer.bos_token + prompt？】
            关键是推理时的输入格式要与训练时见过的格式对应。
            本项目 dataset/lm_dataset.py 的 PretrainDataset 会把训练正文编码为：
                [BOS 的 ID] + 正文的 token ID 列表 + [EOS 的 ID]
            BOS 表示文本开始，EOS 表示文本结束。训练时模型学习“根据前文预测下一个 token”，
            这段数据构造不会额外给正文套上 user / assistant 的对话模板。

            例如假设训练正文是“春天来了，花开了。”，模型学习的续写关系可以理解为：
                看到“起始标记 + 春天” → 预测后面的“来了”，再继续预测后面的内容。
            （这里按词演示意思，实际预测单位是 token。）
            因此推理时只给“起始标记 + 春天”，就是提供一段尚未写完的文本，
            让模型继续生成；不在 prompt 末尾主动补 EOS，因为这里希望它接着写。

            tokenizer.bos_token 是起始标记的字符串形式，prompt 也是字符串，
            所以这里的 + 就是普通字符串拼接，不是张量相加，也没有开始模型计算。
            下一步 tokenizer(inputs, ...) 才将拼接后的文本转换成 token ID，
            其中起始标记会被识别成对应的特殊 token ID，之后交给 generate 续写。
            预训练模型主要学的是文本续写，因此输入问题时，不一定会像聊天助手一样回答，
            也可能继续扩写问题本身；对话微调分支才按角色模板提供对话上下文。
            此处按权重文件名是否含 'pretrain' 来选择格式，并没有自动检查权重的训练方式。

            2. else：用分词器的对话模板把 conversation 中的角色、内容和历史拼成文本。
            tokenize=False：这里只套用模板，暂时不转换成 token ID。
            add_generation_prompt=True：在末尾添加 assistant 的开头，让模型接着回答。
            open_thinking=bool(args.open_thinking)：把命令行整数转成布尔值，0 为 False，
            非零为 True，并传给模板。本项目模板在 True 时追加 <think> 开头，
            在 False 时追加空的 <think>...</think> 段；具体效果取决于加载的模板。
            例如 conversation = [{"role": "user", "content": "你好"}]，默认模板且关闭思考时：
            <|im_start|>user
            你好<|im_end|>
            <|im_start|>assistant
            <think>

            </think>

            以上只是在构造输入，尚未生成回答；后面的 model.generate 才开始生成。
        '''
        if 'pretrain' in args.weight:
            inputs = tokenizer.bos_token + prompt
        else:
            inputs = tokenizer.apply_chat_template(conversation, tokenize=False, add_generation_prompt=True, open_thinking=bool(args.open_thinking))
        
        '''
        【直接看 inputs 执行前后变成什么样】
        以预训练分支为例，用户输入“你好”，执行这行之前 inputs 是字符串：
            inputs = '<|im_start|>你好'

        为方便看懂，假设分词结果和编号如下（分词方式、编号仅作示意，以实际词表为准）：
            '<|im_start|>' → 1
            '你'           → 100
            '好'           → 200

        如果 args.device = 'cpu'，执行下面这行后，inputs 的内容就像这样：
            {
                'input_ids': tensor([[1, 100, 200]]),
                'attention_mask': tensor([[1, 1, 1]])
            }
        inputs 不再是文字，而是一个类似字典的 BatchEncoding 对象。
        input_ids 装着文字对应的编号；attention_mask 的三个 1 表示这三个位置都是有效输入。
        两层方括号 [[...]] 表示“一条输入，里面有三个 token”，形状为 [1, 3]。
        这里没有主动添加结束标记，所以示例末尾没有 EOS 的编号。

        如果 args.device = 'cuda'，内容相同，只是张量放在 GPU 上，显示类似：
            {
                'input_ids': tensor([[1, 100, 200]], device='cuda:0'),
                'attention_mask': tensor([[1, 1, 1]], device='cuda:0')
            }

        后面 inputs['input_ids'] 取出的就是 tensor([[1, 100, 200]]) 这一项。
        return_tensors="pt" 让编号以 PyTorch 张量形式返回；.to(args.device) 指定张量所在设备。
        这个短例子没有超过长度上限，所以 truncation=True 不会截掉任何内容。

        【为什么还会有 attention_mask？】
        它是 tokenizer 按默认行为一起返回的“有效位置说明”，不是模型生成的回答。
        input_ids 告诉模型“输入是什么”，attention_mask 告诉模型“哪些位置可以关注”。
        例如把一条短输入补齐到 5 个位置时，假设填充 token 的编号是 0：
            input_ids      = tensor([[1, 100, 200, 0, 0]])
            attention_mask = tensor([[1,   1,   1, 0, 0]])
        最后两个位置只是为了凑齐长度，不是正文；mask 中的 0 让注意力忽略这些填充位置。
        这只是演示填充的用途，本行没有设置 padding，实际单条输入不需要这样补齐，
        所以返回的 attention_mask 全是 1，也就是“这些位置都有效”。
        后面 generate(..., attention_mask=inputs['attention_mask']) 将它传给模型。
        全是 1 不代表可以偷看未来：模型内部还会单独施加“只能看当前及之前位置”的因果限制。
        它也不是 SFT 训练中“哪些位置计算损失”的标签掩码；用户问题仍是模型需要关注的上下文。

        【SFT 权重推理的例子：用户输入“你好”，关闭思考，无历史对话】
        conversation = [{"role": "user", "content": "你好"}]
        apply_chat_template 先把它变成下面这个字符串（空行也是文本的一部分）：
            <|im_start|>user
            你好<|im_end|>
            <|im_start|>assistant
            <think>

            </think>

        为了直观看清，假设分词后按以下片段编码（仅示意，不是实际词表的分词和编号）：
            <|im_start|> → 1，<|im_end|> → 2，换行 → 10
            user → 20，assistant → 21，你 → 100，好 → 200
            <think> → 30，</think> → 31
        那么执行下面的 tokenizer(...) 后，CPU 上的 inputs 就类似：
            {
                'input_ids': tensor([[1, 20, 10, 100, 200, 2, 10, 1, 21, 10, 30, 10, 10, 31, 10, 10]]),
                'attention_mask': tensor([[1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]])
            }
        这里形状为 [1, 16]：一条输入，按上述假设共有 16 个 token。
        角色名、换行和特殊标记也会编码；它们不是填充，所以对应的 mask 同样是 1。
        此时还没有模型的回答，只有用户内容和 assistant 的开头；generate 会从这里接着生成。
        这展示的是用 SFT 权重进行推理的输入，训练时的数据还会包含示范回答和 labels。
        '''
        inputs = tokenizer(inputs, return_tensors="pt", truncation=True).to(args.device)

        print('🧠: ', end='')
        st = time.time()
        '''
        【generate 的输入和返回值：以下编号和生成内容均为示意】
        假设输入只有三个 token：
            inputs['input_ids']      = tensor([[1, 100, 200]])
            inputs['attention_mask'] = tensor([[1,   1,   1]])
        假设模型接下来依次生成 300、301、302、2，其中：
            300 → '很'，301 → '高兴'，302 → '认识你！'，2 → 结束标记。
        generate 每次预测一个新 token，并把它接到已有序列后面：
            开始：  [1, 100, 200]
            第一步：[1, 100, 200, 300]
            第二步：[1, 100, 200, 300, 301]
            第三步：[1, 100, 200, 300, 301, 302]
            第四步：[1, 100, 200, 300, 301, 302, 2] → 遇到 EOS，结束。
        最终返回的是“原输入 + 新生成内容”，不是只有回答：
            generated_ids = tensor([[1, 100, 200, 300, 301, 302, 2]])
        streamer 会在生成过程中逐步打印“很高兴认识你！”，但不改变这个返回值。

        max_new_tokens：最多新增多少个 token。例如设为 10，本例遇到 EOS 后只新增 4 个。
        do_sample=True：按概率抽取下一个 token，所以实际回答不保证与示例相同。
        temperature 和 top_p：调节采样概率及候选范围；repetition_penalty=1 表示不施加重复惩罚。
        eos_token_id：结束标记编号；pad_token_id：填充标记编号。
        本项目原生 generate 没有使用传入的 pad_token_id；本例也不需要填充。
        '''
        generated_ids = model.generate(
            inputs=inputs["input_ids"], attention_mask=inputs["attention_mask"],
            max_new_tokens=args.max_new_tokens, do_sample=True, streamer=streamer,
            pad_token_id=tokenizer.pad_token_id, eos_token_id=tokenizer.eos_token_id,
            top_p=args.top_p, temperature=args.temperature, repetition_penalty=1
        )
        '''
        【把上面的完整结果切出回答，再转成文字】
        1. generated_ids[0]：取第一条序列，去掉外面那层批次维度：
               tensor([1, 100, 200, 300, 301, 302, 2])
        2. inputs['input_ids'][0] 是 tensor([1, 100, 200])，所以 len(...) = 3。
        3. generated_ids[0][3:]：跳过前 3 个输入 token，从下标 3 一直取到末尾：
               tensor([300, 301, 302, 2])
        4. tokenizer.decode(..., skip_special_tokens=True)：将编号还原为文字，隐藏结束标记：
               response = '很高兴认识你！'
        因此 response 是字符串，不再是张量；下面把它保存到 conversation 中。
        SFT 输入也是同样的切法：若模板编码后长 16，就切 [16:]，把整个输入模板跳过去。
        '''
        response = tokenizer.decode(generated_ids[0][len(inputs["input_ids"][0]):], skip_special_tokens=True)
        conversation.append({"role": "assistant", "content": response})
        '''
        【gen_tokens：本次新增了多少个 token】
        沿用上例：完整结果有 7 个 token，原输入有 3 个 token，所以：
            gen_tokens = 7 - 3 = 4
        这 4 个就是 [300, 301, 302, 2]，包含结束标记 2。
        decode 时隐藏结束标记只影响文字显示，不会从 generated_ids 中删除它。
        因此这里统计的是新增 token 数，不是回答的汉字数，也不是 len(response)。
        下面用它除以耗时计算速度：例如耗时 2 秒，速度就是 4 / 2 = 2 tokens/s。
        '''
        gen_tokens = len(generated_ids[0]) - len(inputs["input_ids"][0])
        print(f'\n[Speed]: {gen_tokens / (time.time() - st):.2f} tokens/s\n\n') if args.show_speed else print('\n\n')

if __name__ == "__main__":
    main()
