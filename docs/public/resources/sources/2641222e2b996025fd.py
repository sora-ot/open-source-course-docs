# 本文件从 token 编号出发，依次完成：查词向量 → 多层注意力和前馈网络 → 词表打分 → 计算损失或逐 token 生成。
# 阅读约定：B=一批样本数，T=本次输入长度，S=历史缓存长度+T，H=隐藏维度，V=词表大小；
# Nq=Query 头数，Nkv=Key/Value 头数，D=每头维度，I=前馈中间维度，E=专家总数，K=每 token 选用的专家数。
# [B,T,H] 表示三维张量，不是三个数值；例如 [2,3,8] 表示 2 条样本、每条 3 个 token、每个 token 有 8 个特征。
# 下文的 token 编号、权重、分数均为教学示例；随机初始化的模型不保证生成示例中的文字或编号。
# 函数前先讲“输入如何变成输出”，函数内再逐行解释计算。所有示例都以本文件的实际实现为准。

# math 提供平方根、对数等标量数学运算；torch 处理张量；F 是不必单独创建层对象的神经网络函数接口。
import math, torch, torch.nn.functional as F
# nn 提供 Module、Linear、Embedding 等可注册参数的网络组件。
from torch import nn
# ACT2FN 把配置中的激活函数名字（例如 'silu'）映射成可调用的激活函数。
from transformers.activations import ACT2FN
# 三个基类分别提供预训练模型框架、生成相关接口和配置的保存/读取能力；本文件自己实现了 generate。
from transformers import PreTrainedModel, GenerationMixin, PretrainedConfig
# 用带字段名的输出对象包装损失、词表分数、缓存等，调用方可以直接访问 outputs.logits。
from transformers.modeling_outputs import MoeCausalLMOutputWithPast


# 配置对象只保存参数，不在这里创建网络权重，也不检查所有参数组合是否合理。
class MiniMindConfig(PretrainedConfig):
    # 给配置标记模型类型，便于框架在配置文件中识别；这行本身不完成 Auto 类的注册。
    model_type = "minimind"

    '''
    【完整例子：先创建配置，再逐项看最终保存的值】

    假设要创建一个小模型：
        cfg = MiniMindConfig(
            hidden_size=8, num_hidden_layers=2, use_moe=False,
            num_attention_heads=2, num_key_value_heads=1,
            vocab_size=16, intermediate_size=12,
            max_position_embeddings=32, dropout=0.0
        )

    1. Python 分配参数
        hidden_size = 8
        num_hidden_layers = 2
        use_moe = False
        kwargs = {
            'num_attention_heads': 2, 'num_key_value_heads': 1,
            'vocab_size': 16, 'intermediate_size': 12,
            'max_position_embeddings': 32, 'dropout': 0.0
        }
        **kwargs 收集没有单独列在函数签名里的关键字参数。

    2. super().__init__(**kwargs)
        先初始化配置基类，随后下面的赋值把本模型实际使用的字段确定下来。
        这个过程只构造配置对象，没有创建词向量表，也没有训练网络。

    3. 保存网络规模与基本参数
        cfg.hidden_size = 8
        cfg.num_hidden_layers = 2
        cfg.use_moe = False
        cfg.dropout = 0.0
        cfg.vocab_size = 16
        cfg.bos_token_id = 1        # 没有传，采用默认值
        cfg.eos_token_id = 2        # 没有传，采用默认值
        cfg.flash_attn = True       # 没有传，采用默认值

    4. 确定注意力形状
        cfg.num_attention_heads = 2
        cfg.num_key_value_heads = 1
        cfg.head_dim = 8 // 2 = 4
        即：2 个 Query 头，每头 4 维；1 个 KV 头供 2 个 Query 头共享。
        如果另传 head_dim=6，就使用 6，Query 投影宽度将为 2*6=12，再由输出投影映射回 8。

    5. 确定前馈、位置编码和归一化配置
        cfg.hidden_act = 'silu'
        cfg.intermediate_size = 12
        cfg.max_position_embeddings = 32
        cfg.rms_norm_eps = 0.000001
        cfg.rope_theta = 1000000
        cfg.tie_word_embeddings = True
        若没有传 intermediate_size，则本例默认计算：
            ceil(8*pi/64)*64 = 64，而不是 12。
        默认的大模型 H=768 时，该公式得到 2432。

    6. 判断是否启用位置频率扩展
        cfg.inference_rope_scaling = False
        因此 cfg.rope_scaling = None。
        如果改传 inference_rope_scaling=True，则保存：
            {
                'beta_fast': 32, 'beta_slow': 1, 'factor': 16,
                'original_max_position_embeddings': 2048,
                'attention_factor': 1.0, 'type': 'yarn'
            }
        是否实际修改频率还由 precompute_freqs_cis 中 end/orig_max 的判断决定。

    7. 保存 MoE 字段，即使本次 use_moe=False 也照样保存
        cfg.num_experts = 4
        cfg.num_experts_per_tok = 1
        cfg.moe_intermediate_size = 12
        cfg.norm_topk_prob = True
        cfg.router_aux_loss_coef = 0.0005
        这些字段只有在后续创建/运行 MoE 时才发挥作用。

    8. 最终得到 cfg，供后续各模块读取；__init__ 本身隐式返回 None。
        输入 [[1,5,7]] 的形状是 [1,3]：1 条序列，每条 3 个 token。
        词表有 16 行、每行 8 个数，编号 1、5、7 各查出一行：
            1 -> [0.2,-0.1,0.5,...,0.3]，共 8 个数
            5 -> [0.7, 0.4,0.1,...,0.8]，共 8 个数
            7 -> [0.3, 0.6,0.9,...,0.2]，共 8 个数
        数值仅作示意；词向量形状因此为 [1,3,8]。
        完整语言模型保留全部位置时，输出 logits 为 [1,3,16]：
            位置 0 根据 [1] 为 16 个候选打分，训练目标是 5；
            位置 1 根据 [1,5] 为 16 个候选打分，训练目标是 7；
            位置 2 根据 [1,5,7] 为 16 个候选打分，供续写下一个 token。
        16 是候选数量，不是一次生成 16 个 token；分数经 softmax 才成为概率。
        labels 若也只有 [[1,5,7]]，最后位置没有后续目标，不参与移位损失。
        logits_to_keep=1 时只投影最后位置，输出形状为 [1,1,16]。

    数据流：
        构造参数 -> kwargs 取值或默认值 -> cfg 各字段 -> 后续模块按 cfg 创建权重
    输入约定：头数应有效且 Query 头数能被 KV 头数整除，RoPE 的每头维度为正偶数。
    '''
    def __init__(self, hidden_size=768, num_hidden_layers=8, use_moe=False, **kwargs):
        # 初始化配置基类，让其接收额外配置项；下面再设置本模型具体使用的字段。
        super().__init__(**kwargs)
        # token 在各 Block 之间传递时的特征宽度 H，例如 8。
        self.hidden_size = hidden_size
        # Transformer Block 的数量，例如 2；层数越多，同一份表示被更新的次数越多。
        self.num_hidden_layers = num_hidden_layers
        # True 使用多个专家组成的前馈网络；False 每层仅使用一个普通 FeedForward。
        self.use_moe = use_moe
        # 训练时随机丢弃元素的概率；0.0 不丢弃，eval 模式下 Dropout 也不丢弃。
        self.dropout = kwargs.get("dropout", 0.0)
        # 词表包含多少个 token；输入编号须处于 [0,V-1]，输出层也为 V 个候选打分。
        self.vocab_size = kwargs.get("vocab_size", 6400)
        # 保存序列开始标记的编号；本文件的 forward 不会自动在输入前加这个编号。
        self.bos_token_id = kwargs.get("bos_token_id", 1)
        # 保存序列结束标记的编号；自定义 generate 有自己的 eos_token_id 参数，需要调用方留意两者一致。
        self.eos_token_id = kwargs.get("eos_token_id", 2)
        # 允许满足条件时调用 PyTorch 的 SDPA 接口；实际使用哪种计算内核取决于运行环境。
        self.flash_attn = kwargs.get("flash_attn", True)
        # Query 头数 Nq：同一个 token 从多少组投影特征计算注意力。
        self.num_attention_heads = kwargs.get("num_attention_heads", 8)
        # Key/Value 头数 Nkv；小于 Nq 时，多个 Query 头共享同一组 K/V，这就是分组查询注意力。
        self.num_key_value_heads = kwargs.get("num_key_value_heads", 4)
        # 每头维度 D；// 是整数除法，例如 768//8=96。
        self.head_dim = kwargs.get("head_dim", self.hidden_size // self.num_attention_heads)
        # 选择前馈门控分支的非线性函数；默认 SiLU(x)=x*sigmoid(x)。
        self.hidden_act = kwargs.get("hidden_act", 'silu')
        # 前馈层先把 H 升到 I；未指定时，按 H*pi 估算并向上取整到 64 的倍数。
        self.intermediate_size = kwargs.get("intermediate_size", math.ceil(hidden_size * math.pi / 64) * 64)
        # 初始化时预计算这么多位置的旋转表；历史长度与本次长度之和应不超过表长。
        self.max_position_embeddings = kwargs.get("max_position_embeddings", 32768)
        # RMSNorm 分母中的小正数，防止全零输入导致除零。
        self.rms_norm_eps = kwargs.get("rms_norm_eps", 1e-6)
        # RoPE 的频率基数；不同特征对按这个基数获得不同的旋转速度。
        self.rope_theta = kwargs.get("rope_theta", 1e6)
        # 是否让输入词向量表与输出词表投影共用同一份 [V,H] 参数。
        self.tie_word_embeddings = kwargs.get("tie_word_embeddings", True)
        # 是否构造下方的长上下文缩放配置；实际缩放还取决于预计算长度是否超过原始长度。
        self.inference_rope_scaling = kwargs.get("inference_rope_scaling", False)
        # 用字典汇总 YaRN 风格的频率缩放参数；关闭开关时整个字段为 None。
        self.rope_scaling = {
            # 快速旋转边界：根据原始窗口中转过 32 圈的位置反推频率索引。
            "beta_fast": 32,
            # 慢速旋转边界：根据原始窗口中转过 1 圈的位置反推频率索引。
            "beta_slow": 1,
            # 低频部分的频率最多除以 16，让相同相位变化分布到更长的位置范围。
            "factor": 16,
            # 用 2048 作为原始上下文长度，判断是否需要扩展并计算两个边界。
            "original_max_position_embeddings": 2048,
            # cos/sin 表的幅度乘数；这里为 1，因此不额外改变幅度。
            "attention_factor": 1.0,
            # 配置的类型标记；下方计算函数直接读取数值字段，不按这个字符串再分派算法。
            "type": "yarn"
        } if self.inference_rope_scaling else None
        # 专家总数 E；例如 E=4，表示每个 MoE 层有四个独立的 FeedForward。
        self.num_experts = kwargs.get("num_experts", 4)
        # 每个 token 选 K 个专家，要求 1<=K<=E；默认只选得分最高的一个。
        self.num_experts_per_tok = kwargs.get("num_experts_per_tok", 1)
        # 每个专家自己的中间宽度，未指定时与普通前馈宽度相同。
        self.moe_intermediate_size = kwargs.get("moe_intermediate_size", self.intermediate_size)
        # 是否让被选中的 K 个权重重新加起来等于 1；选一个专家时归一化后其权重约为 1。
        self.norm_topk_prob = kwargs.get("norm_topk_prob", True)
        # 路由均衡辅助损失的系数；由 MoE 计算，再单独放到最终输出的 aux_loss 中。
        self.router_aux_loss_coef = kwargs.get("router_aux_loss_coef", 5e-4)


# RMSNorm 对每个 token 的最后一维做均方根归一化，再用可学习权重缩放；它不减均值。
class RMSNorm(torch.nn.Module):
    '''
    【完整例子：创建两个可训练缩放参数】

    假设：
        layer = RMSNorm(dim=2, eps=0.00001)

    1. 接收参数
        dim = 2
        eps = 0.00001
        表示后续输入的最后一维必须有两个特征。

    2. super().__init__()
        初始化 Module 的参数和子模块管理机制。
        此时尚未创建 weight，也尚未处理任何输入张量。

    3. self.eps = eps
        layer.eps = 0.00001
        eps 是固定 Python 数值，不是 Parameter，不会被优化器学习。

    4. torch.ones(dim)
        得到 tensor([1.0, 1.0])，形状 [2]。
        在通常的默认环境中，这是 CPU 上的 FP32 张量。

    5. nn.Parameter(torch.ones(dim))
        把上面的向量包装成可训练参数，默认 requires_grad=True。
        赋给 self.weight 后：
            layer.weight = Parameter([1.0, 1.0])
            list(layer.named_parameters()) 包含 ('weight', layer.weight)
            layer.state_dict()['weight'] 的值为 [1.0, 1.0]
        参数数量是 2，不是一个 2×2 矩阵。

    6. 构造结束
        __init__ 隐式返回 None；表达式 RMSNorm(...) 的结果是创建好的 layer 对象。
        后续 layer(torch.tensor([[3.,4.],[0.,2.]])) 才会调用 forward。
        两行都使用同一组 [1,1] 缩放系数，不会各自创建一组 weight。
        若输入形状变成 [4,8,2]，本层仍只有 2 个缩放参数。

    数据流：
        dim=2 -> ones(2)=[1,1] -> Parameter -> 注册为 layer.weight
    '''
    def __init__(self, dim: int, eps: float = 1e-5):
        # 建立 Module 内部的参数/子模块管理结构，必须在给实例注册参数之前调用。
        super().__init__()
        # 保存 eps；它加在均方值上，再一起开平方，不是加在最终输出上。
        self.eps = eps
        # ones(dim) 创建全 1 向量；Parameter 使其出现在模型参数中并参与梯度更新。
        self.weight = nn.Parameter(torch.ones(dim))

    '''
    【完整例子：两行数据分别计算均方根归一化】

    假设：
        layer = RMSNorm(dim=2, eps=0.00001)
        x = torch.tensor([[3.,4.],[0.,2.]])
        result = layer.norm(x)
        x.shape = [2,2]，每一行独立处理；本函数不使用 layer.weight。

    1. x.pow(2)
        [[3,4],        [[9,16],
         [0,2]]  ->     [0, 4]]
        平方后形状仍为 [2,2]。

    2. mean(-1, keepdim=True)
        对每行的两个特征求平均：
            第一行：(9+16)/2 = 12.5
            第二行：(0+4)/2 = 2
        得到 [[12.5],[2.0]]，形状 [2,1]。
        keepdim=True 保留一列，方便随后广播回每行的两个特征。

    3. 加上 self.eps
        [[12.50001],[2.00001]]
        eps 加在开平方之前；全零向量也不会出现分母为 0。

    4. torch.rsqrt(...)
        rsqrt(a)=1/sqrt(a)，因此结果约为：
            [[0.28284260],[0.70710501]]

    5. x * 上面的倒数
        第一行：[3*0.28284260, 4*0.28284260]
        第二行：[0*0.70710501, 2*0.70710501]
        广播只在各行内部发生，不会把两个 token 混起来。

    6. 最终返回
        result ≈ [[0.84852780,1.13137040],
                  [0.00000000,1.41421003]]
        result.shape = [2,2]，与输入相同。
        每行均方值接近 1，但均值不要求为 0；这里没有减均值操作。

    边界例子：
        x=[[0,0]] -> 平方均值 0 -> 分母 sqrt(eps)>0 -> 输出仍为 [[0,0]]。
        即使把 layer.weight 改为 [2,0.5]，直接调用 norm(x) 的结果仍不变；
        只有 forward 会在本函数的结果上继续乘 weight。

    数据流：
        x -> 平方 -> 按最后一维求均值 -> 加 eps -> 取平方根倒数 -> 逐元素乘 x
    '''
    def norm(self, x):
        # pow(2) 逐元素平方；mean(-1) 沿特征维求均值；rsqrt 是平方根的倒数；最后逐元素乘 x。
        return x * torch.rsqrt(x.pow(2).mean(-1, keepdim=True) + self.eps)

    '''
    【完整例子：归一化、可训练缩放、类型恢复及一次参数更新】

    假设：
        layer = RMSNorm(dim=2, eps=0.00001)
        x = torch.tensor([[3.,4.]], dtype=torch.float16)
        result = layer(x)
        layer.weight 初始为 FP32 的 [1,1]，输入形状 [1,2]。
        调用 layer(x) 经 Module 调用机制进入本 forward。

    1. x.float()
        得到 FP32 的 [[3.,4.]]，形状仍为 [1,2]，输入 x 本身仍是 FP16。

    2. self.norm(x.float())
        平方 -> [[9,16]]
        求均值并加 eps -> [[12.50001]]
        取平方根倒数 -> [[0.28284260]]
        乘输入 -> z≈[[0.84852780,1.13137040]]
        到这里完全没有使用可训练的 weight。

    3. self.weight * z
        weight=[1,1]，所以：
            y≈[[1*0.84852780,1*1.13137040]]
             =[[0.84852780,1.13137040]]
        [2] 的 weight 广播到 [1,2]，每个特征乘自己的缩放系数。

    4. .type_as(x)
        将结果转换回 FP16，受 FP16 舍入影响，保存的数值约为：
            result = [[0.8486328125,1.1318359375]]
        返回形状仍为 [1,2]。
        浮点精度转换不是 detach，正常记录梯度时可继续反向传播。

    5. 对照另一组 weight
        为看清效果，假设训练后 weight=[2,0.5]，再次输入相同 x。
        归一化 z 完全相同，但 FP32 缩放结果变成：
            [[2*0.84852780,0.5*1.13137040]]
            ≈ [[1.69705560,0.56568520]]
        返回前再舍入为 FP16。
        * 是逐元素乘法，不是矩阵乘法；整层只有两个缩放参数。

    6. 手算一次训练更新
        下面单独用 FP32 说明更新过程，不把上面的 FP16 舍入混入手算。
        假设从 weight=[1,1] 开始，后续网络传回：
            d(loss)/d(y) = [0.1,-0.2]
        因为 y_i=weight_i*z_i：
            d(loss)/d(weight) = [0.1*0.84852780,-0.2*1.13137040]
                             ≈ [0.08485278,-0.22627408]
        若使用无动量、无权重衰减的 SGD，学习率 0.01：
            新 weight = [1,1] - 0.01*[0.08485278,-0.22627408]
                      ≈ [0.99915147,1.00226274]
        loss.backward() 计算并累积梯度；optimizer.step() 执行更新。
        forward 不会自己调用优化器，也不会每次重新把 weight 设成 1。

    数据流：
        FP16 x -> FP32 x -> 纯归一化 z -> 逐特征乘可学习 weight -> FP16 输出

    【补充理解：为什么归一化层仍然有可训练参数】
    【一、RMSNorm 不就是一个公式吗，为什么还有可训练参数？】
    “按公式计算”和“公式中含有可训练参数”可以同时成立。
    例如 y=a*x 也是一个公式，但 a 可以由训练学习；这里的 weight 就相当于每个特征自己的 a。
    本文件把完整 RMSNorm 分成两步，只有第一步是纯粹的归一化：

        第一步：z_i = x_i / sqrt((x_1² + ... + x_H²) / H + eps)
                对应 self.norm(x.float())，没有使用 self.weight。
        第二步：y_i = weight_i * z_i
                对应 self.weight * self.norm(...)，这里才使用可训练参数。

    合起来就是 y_i = weight_i * x_i / sqrt(mean(x²) + eps)。
    文献里常用 gamma_i（γ_i）表示这个缩放系数；代码里的 self.weight 就是 gamma。
    注意 RMS(x)=sqrt(mean(x²)) 是不含 eps 的数学定义，代码额外加 eps 是为了避免除零。
    所以“计算 RMS”“用 RMS 归一化”“完整的 RMSNorm 层”是相关但不完全相同的概念。
    当前实现没有额外的可训练偏置 beta，也没有减去输入均值。

    【二、哪些量会训练，哪些量只是根据输入算出来？】
    1. x：当前 token 的输入表示，每次前向可能不同；它通常来自上游层，不是本层新增的参数。
    2. mean(x²)、平方根、倒数、z：根据这次 x 临时计算的中间结果，不是独立存储的可训练参数。
    3. eps：构造时设置的小常数，用于数值稳定；本实现不会通过优化器更新它。
    4. self.weight：构造时创建并持续保存的参数，会在后续前向中反复使用。
       nn.Parameter(torch.ones(dim)) 为 dim 个特征各创建一个初值为 1 的系数，默认 requires_grad=True。
       把 Parameter 赋给 Module 属性后，它会出现在 model.parameters() 和 state_dict() 中。
       若优化器包含它、它未被冻结且正常执行反向传播与更新，训练就会调整这些系数。
       forward 只用当前 weight 计算结果，不会在每次调用时重新把它设为 1，也不会自己更新参数。
    【四、已经归一化，为什么还允许学着放大、缩小？】
    归一化让进入后续计算的整体数值尺度更稳定；不同特征可能需要不同的输出尺度。
    可学习的 weight 让网络根据最终任务损失选择这些尺度，而不是强制所有特征永远维持同样的缩放。
    这不能理解成 weight 一定等于“特征的重要程度”：它会与前后层一起学习，也不限制为正数。
    乘过 weight 后，y 的均方根不再保证约为 1；接近单位均方根的是中间结果 z。
    这也不等于简单恢复原输入：分母随每个 token 的 x 变化，weight 则在不同 token 之间共享。
    固定的一组 weight 一般不能把每个输入各自不同的归一化分母都抵消掉。

    weight在batch和token之间共享，参数量只等于最后一维。梯度也会通过依赖x的分母传回上游。
    eval()本身不会冻结参数或关闭梯度；no_grad()/inference_mode()才会在相应范围关闭梯度记录。
    '''
    def forward(self, x):
        # x.float()：把输入转成 FP32；self.norm(...)：按最后一维计算纯 RMS 归一化，这一步不使用可训练参数。
        # self.weight * ...：逐特征乘可学习的 gamma；weight 在 __init__ 中创建，广播到每个 token，形状不变。
        # type_as(x)：将结果转回 x 的 dtype；浮点类型转换保留梯度路径，此处只计算输出，参数更新由优化器完成。
        return (self.weight * self.norm(x.float())).type_as(x)


'''
【完整例子：从频率编号算出整张 cos/sin 表】

假设：
    dim=4，end=3，rope_base=10000，rope_scaling=None
    cos, sin = precompute_freqs_cis(4,3,10000)
    预计算位置 0、1、2，每个位置给 4 个特征准备旋转系数。

1. 生成频率编号
    torch.arange(0,4,2) -> [0,2]
    [:4//2] -> [0,2]
    .float()/4 -> [0.0,0.5]

2. 计算角频率
    10000**[0.0,0.5] -> [1,100]
    1.0/[1,100] -> freqs=[1.0,0.01]
    attn_factor=1.0
    freqs.shape=[2]，分别供两个特征对使用。

3. 判断缩放配置
    rope_scaling=None，不进入缩放分支；freqs 仍为 [1.0,0.01]。

4. 生成位置编号
    t=torch.arange(3) -> [0,1,2]，形状 [3]。

5. torch.outer(t,freqs)
    每个位置分别乘每种频率：
        位置 0：[0*1,0*0.01] -> [0,0]
        位置 1：[1*1,1*0.01] -> [1,0.01]
        位置 2：[2*1,2*0.01] -> [2,0.02]
    freqs 变量现在保存角度矩阵：
        [[0,0],[1,0.01],[2,0.02]]，形状 [3,2]，单位为弧度。

6. 计算并复制 cos
    torch.cos(freqs) ≈
        [[ 1.000000,1.000000],
         [ 0.540302,0.999950],
         [-0.416147,0.999800]]
    cat([cos,cos],dim=-1)，再乘 1.0：
        freqs_cos ≈
        [[ 1.000000,1.000000, 1.000000,1.000000],
         [ 0.540302,0.999950, 0.540302,0.999950],
         [-0.416147,0.999800,-0.416147,0.999800]]

7. 计算并复制 sin
    torch.sin(freqs) ≈
        [[0.000000,0.000000],
         [0.841471,0.010000],
         [0.909297,0.019999]]
    拼接后：
        freqs_sin ≈
        [[0.000000,0.000000,0.000000,0.000000],
         [0.841471,0.010000,0.841471,0.010000],
         [0.909297,0.019999,0.909297,0.019999]]

8. 最终返回 (freqs_cos,freqs_sin)，两个张量形状均为 [3,4]。
    前后两半使用相同系数，是因为实际配对为第 0/2 维、第 1/3 维。
    第 0 行 cos 全 1、sin 全 0，因此位置 0 的特征不旋转。

【补充完整分支：开启长上下文缩放】
另一次调用令：
    dim=4，end=4096，rope_base=10000
    rope_scaling={
        'original_max_position_embeddings':2048,'factor':16,
        'beta_fast':32,'beta_slow':1,'attention_factor':1.0
    }

1. 初始频率仍为 [1,0.01]；解包得 orig_max=2048、factor=16、beta_fast=32、beta_slow=1。
2. end/orig_max=4096/2048=2>1，进入缩放。
3. inv_dim(32)≈0.504000，inv_dim(1)≈1.256575。
4. low=max(floor(0.504000),0)=0；
   high=min(ceil(1.256575),4//2-1)=min(2,1)=1。
5. ramp=clamp(([0,1]-0)/max(1-0,0.001),0,1)=[0,1]。
6. 频率乘数=1-ramp+ramp/16=[1,0.0625]。
   新 freqs=[1,0.01]*[1,0.0625]=[1,0.000625]。
7. 生成 t=0..4095，外积后位置 1 的角度为 [1,0.000625]。
   该位置 cos≈[0.540302,0.9999998,0.540302,0.9999998]；
   sin≈[0.841471,0.000625,0.841471,0.000625]。
8. 返回两个 [4096,4] 张量；其它位置同样用“位置编号×新频率”计算。
   如果 end 改为 2048，就不修改频率，因为 end/orig_max 不大于 1；
   字典中的 attention_factor 仍会用于最后的 cos/sin 幅度乘法。

数据流：
    特征对编号 -> 角频率 -> 可选缩放 -> 与位置做外积 -> cos/sin -> 重复两半 -> 返回
'''
def precompute_freqs_cis(dim: int, end: int = int(32 * 1024), rope_base: float = 1e6, rope_scaling: dict = None):
    # arange(0,dim,2) 取 0,2,4…；转浮点后计算 base^(-索引/dim)，得到 [D/2] 频率；幅度初始为 1。
    freqs, attn_factor = 1.0 / (rope_base ** (torch.arange(0, dim, 2)[: (dim // 2)].float() / dim)), 1.0
    # 只有传入缩放字典才读取扩展参数；None 表示保持普通 RoPE。
    if rope_scaling is not None:
        # 用元组解包一次取出原始长度、缩放倍数、快慢边界和幅度，顺序与左侧一一对应。
        orig_max, factor, beta_fast, beta_slow, attn_factor = (
            # 未提供原始长度或倍数时，分别按 2048 和 16 处理。
            rope_scaling.get("original_max_position_embeddings", 2048), rope_scaling.get("factor", 16),
            # 未提供两个边界或幅度时，分别按 32 圈、1 圈、1 倍幅度处理。
            rope_scaling.get("beta_fast", 32.0), rope_scaling.get("beta_slow", 1.0), rope_scaling.get("attention_factor", 1.0)
        )
        # 例如 end=32768、orig_max=2048，比值为 16，进入缩放；不超过原长则不改变频率。
        if end / orig_max > 1.0:
            '''
            【完整例子：把旋转圈数反推为频率对索引】

            这是一个局部 lambda，使用外层的 dim、orig_max、rope_base，不需要再次传这些值。
            假设：
                dim=4，orig_max=2048，rope_base=10000
                result=inv_dim(b=1)

            1. b*2*pi=1*2*pi≈6.283185。
            2. orig_max/(b*2*pi)=2048/6.283185≈325.949323。
            3. log(325.949323)≈5.786742；分子 dim*log(...)≈23.146968。
            4. 分母 2*log(10000)≈18.420681。
            5. 相除得 result≈1.256575，它是连续的频率对索引，还没有取整。

            再计算 b=32：
                orig_max/(32*2*pi)≈10.185916
                result≈0.504000

            调用方随后做：
                low=max(floor(0.504000),0)=0
                high=min(ceil(1.256575),1)=1
            得到实际使用的边界 [0,1]。

            这个反解来自：
                orig_max * rope_base**(-2*i/dim) = b*2*pi
            左边是原始窗口中转过的弧度，右边是 b 圈对应的弧度。
            数据流：圈数 b -> 弧度 b*2*pi -> 对数反解 -> 连续索引 -> 调用方取整与限制边界。
            '''
            inv_dim = lambda b: (dim * math.log(orig_max / (b * 2 * math.pi))) / (2 * math.log(rope_base))
            # 快边界向下取整且至少为 0；慢边界向上取整且至多为 D/2-1，得到渐变区域的两个端点。
            low, high = max(math.floor(inv_dim(beta_fast)), 0), min(math.ceil(inv_dim(beta_slow)), dim // 2 - 1)
            # (索引-low)/(high-low) 构造斜坡；分母至少 0.001 避免除零，clamp 将结果限制为 0~1。
            ramp = torch.clamp((torch.arange(dim // 2, device=freqs.device).float() - low) / max(high - low, 0.001), 0, 1)
            # ramp=0 保留频率，ramp=1 将频率除以 factor；中间值做线性混合。
            freqs = freqs * (1 - ramp + ramp / factor)
    # 创建位置编号 0 到 end-1，并与频率张量放在相同设备。
    t = torch.arange(end, device=freqs.device)
    # outer 是外积：位置 [end] × 频率 [D/2] → 角度 [end,D/2]；这里 freqs 变量改为保存角度。
    freqs = torch.outer(t, freqs).float()
    # 将 cos 表沿最后一维重复两半，得到 [end,D]，再整体乘幅度系数。
    freqs_cos = torch.cat([torch.cos(freqs), torch.cos(freqs)], dim=-1) * attn_factor
    # sin 表使用完全相同的拼接方式，保证每对待旋转特征的相位一致。
    freqs_sin = torch.cat([torch.sin(freqs), torch.sin(freqs)], dim=-1) * attn_factor
    # 返回两个实数表；虽然函数名含 cis，本实现没有返回复数张量。
    return freqs_cos, freqs_sin


'''
【完整例子：给 Q、K 的两对特征分别旋转】

假设只有一个 batch、一个位置、一个头，每头 4 维：
    q=torch.tensor([[[[1.,2.,3.,4.]]]])   # [1,1,1,4]
    k=torch.tensor([[[[5.,6.,7.,8.]]]])   # [1,1,1,4]
为了手算，直接给定一张合法的旋转系数表：
    cos=torch.tensor([[0.,1.,0.,1.]])    # [1,4]
    sin=torch.tensor([[1.,0.,1.,0.]])    # [1,4]
    unsqueeze_dim=1
这表示第 0/2 维转 pi/2，第 1/3 维转 0；不是声称默认频率表在某整数位置恰好如此。

1. 定义 rotate_half，后续分别对 Q、K 调用
    rotate_half(q) 的末维：[1,2,3,4] -> [-3,-4,1,2]
    rotate_half(k) 的末维：[5,6,7,8] -> [-7,-8,5,6]
    batch、位置、头这三维不变。

2. 给系数表插入一个轴
    cos.unsqueeze(1) -> [[[0,1,0,1]]]，形状 [1,1,4]
    sin.unsqueeze(1) -> [[[1,0,1,0]]]，形状 [1,1,4]
    与四维 Q/K 运算时，左边再隐式补一个长度为 1 的 batch 轴，进行广播。

3. 计算 Query 的两项
    q*cos -> [1,2,3,4]*[0,1,0,1] = [0,2,0,4]
    rotate_half(q)*sin -> [-3,-4,1,2]*[1,0,1,0] = [-3,0,1,0]

4. 两项相加，再 .to(q.dtype)
    q_embed=[-3,2,1,4]
    即第 0/2 维的 (1,3) 变成 (-3,1)，第 1/3 维的 (2,4) 保持不变。
    完整张量 q_embed=[[[[-3,2,1,4]]]]，形状 [1,1,1,4]。
    * PPT第45页

5. 对 Key 重复同样的过程
    k*cos=[0,6,0,8]
    rotate_half(k)*sin=[-7,0,5,0]
    相加并恢复 k.dtype：
        k_embed=[[[[-7,6,5,8]]]]

6. 最终返回
    (q_embed,k_embed)
    本函数不接收 Value，因此 V 不会在这里旋转。

多头/多位置时：
    Q:[2,3,2,4]，K:[2,3,1,4]，cos/sin:[3,4]
    unsqueeze(1) -> [3,1,4]，广播为 [1,3,1,4]；
    每个位置用自己那一行系数，所有 batch 和头共享该位置的系数。
    输出 Q/K 的形状分别保持 [2,3,2,4]、[2,3,1,4]。

数据流：Q/K -> 两半交换并给后半取负 -> 分别乘 cos/sin -> 两项相加 -> 恢复 dtype。
'''
def apply_rotary_pos_emb(q, k, cos, sin, unsqueeze_dim=1):
    '''
    【完整例子：一行表达式怎样把前后两半重新拼起来】

    假设：
        x=torch.tensor([[[[1.,2.,3.,4.]]]])
        x.shape=[1,1,1,4]

    1. x.shape[-1]=4，4//2=2，确定从第 2 个特征开始切后半。
    2. x[...,2:] -> [[[[3,4]]]]，形状 [1,1,1,2]。
    3. -x[...,2:] -> [[[[-3,-4]]]]，形状不变。
    4. x[...,:2] -> [[[[1,2]]]]，取出前半。
    5. torch.cat((后半取负,前半),dim=-1)
        把 [-3,-4] 和 [1,2] 沿最后一维连接：
            result=[[[[-3,-4,1,2]]]]
    6. 返回形状 [1,1,1,4]，与输入一致；原始 x 没有被原地改写。

    ... 表示保留此前的所有轴；不是把整个四维张量展平。
    这个函数只产生旋转公式的一项，实际旋转还需外层乘 sin、加上 x*cos。
    数据流：[1,2,3,4] -> 后半 [3,4] 与前半 [1,2] -> [-3,-4] + [1,2] -> [-3,-4,1,2]。
    '''
    def rotate_half(x): return torch.cat((-x[..., x.shape[-1] // 2:], x[..., : x.shape[-1] // 2]), dim=-1)
    # 给 cos/sin 插入头维后广播；逐元素算 q*cos + (-后半,前半)*sin，最后恢复 q 的数据类型。
    q_embed = ((q * cos.unsqueeze(unsqueeze_dim)) + (rotate_half(q) * sin.unsqueeze(unsqueeze_dim))).to(q.dtype)
    # 对 Key 做同位置、同公式的旋转；K 的头数可以少于 Q，因为表在头维广播。
    k_embed = ((k * cos.unsqueeze(unsqueeze_dim)) + (rotate_half(k) * sin.unsqueeze(unsqueeze_dim))).to(k.dtype)
    # 返回元组，让调用方用 xq,xk=... 同时接收两个结果。
    return q_embed, k_embed


'''
【完整例子：两个 KV 头展开成四个头】

假设：
    x=torch.tensor([[
        [[1.,2.],[3.,4.]],
        [[5.,6.],[7.,8.]]
    ]])
    x.shape=[1,2,2,2]
    n_rep=2
其中：
    位置 0 的 KV 头 0=[1,2]，头 1=[3,4]；
    位置 1 的 KV 头 0=[5,6]，头 1=[7,8]。

1. 解包 x.shape
    bs=1，slen=2，num_key_value_heads=2，head_dim=2。

2. 判断 n_rep==1
    本次 2!=1，继续展开。
    如果 n_rep=1，直接 return x，返回的就是原来的张量对象。

3. x[:,:,:,None,:]
    在头与特征之间插入复制轴，形状 [1,2,2,1,2]。
    仅看位置 0：
        头 0：[[1,2]]
        头 1：[[3,4]]

4. expand(1,2,2,2,2)
    把复制轴从 1 广播为 2，形状 [1,2,2,2,2]。
    位置 0：
        头 0：[[1,2],[1,2]]
        头 1：[[3,4],[3,4]]
    位置 1：
        头 0：[[5,6],[5,6]]
        头 1：[[7,8],[7,8]]
    expand 本身使用广播视图，不在这一步为每份重复数据分配独立存储。

5. reshape(1,2,2*2,2)
    将“原头数”和“复制数”两轴合并，最终形状 [1,2,4,2]。
    这一步根据内存布局可能需要复制数据。

6. 最终返回
    [[
        [[1,2],[1,2],[3,4],[3,4]],
        [[5,6],[5,6],[7,8],[7,8]]
    ]]
    每个位置的头顺序都是 [头0,头0,头1,头1]，不是 [头0,头1,头0,头1]。
    因而四个 Query 头中，第 0/1 头共享原 KV 头 0，第 2/3 头共享原 KV 头 1。

数据流：[B,S,Nkv,D] -> 插入复制轴 -> 广播 n_rep 份 -> 合并两轴 -> [B,S,Nkv*n_rep,D]。
'''
def repeat_kv(x: torch.Tensor, n_rep: int) -> torch.Tensor:
    # 解包输入的四个维度；它应当是转置之前的 [B,S,Nkv,D]。
    bs, slen, num_key_value_heads, head_dim = x.shape
    # 不需要重复时立即返回，保留原张量对象。
    if n_rep == 1: return x
    # None 插入复制轴；expand 使用广播视图，reshape 合并头与复制轴（这一步可能需要实际复制内存）。
    return (x[:, :, :, None, :].expand(bs, slen, num_key_value_heads, n_rep, head_dim).reshape(bs, slen, num_key_value_heads * n_rep, head_dim))


# 注意力让当前位置从可见的历史 token 中提取信息；这里支持 GQA、Q/K 归一化、RoPE 和 KV 缓存。
class Attention(nn.Module):
    '''
    【完整例子：配置怎样变成 Q/K/V 投影和归一化参数】

    假设：
        cfg=MiniMindConfig(hidden_size=4,num_attention_heads=2,
                           num_key_value_heads=1,head_dim=2,
                           dropout=0.0,flash_attn=False)
        attn=Attention(cfg)
        后续准备输入 [1,2,4]：1 条序列，2 个 token，每个 4 个特征。

    1. 调用 super().__init__() 后保存头数
        self.num_key_value_heads=1
        self.n_local_heads=2
        self.n_local_kv_heads=1
        self.n_rep=2//1=2
        每一个 KV 头供两个 Query 头使用；local 这个名字不代表这里进行了多卡切分。

    2. 保存单头维度和因果标记
        self.head_dim=2
        self.is_causal=True
        第 0 个 token 只能看自己，第 1 个 token 可以看前两个位置。

    3. 创建 Query 投影
        q_proj=Linear(4,2*2,bias=False)=Linear(4,4,bias=False)
        q_proj.weight.shape=[4,4]，共 16 个参数。
        输入 [1,2,4] -> 投影 [1,2,4] -> forward 拆头成 [1,2,2,2]。

    4. 创建 Key、Value 投影
        k_proj=Linear(4,1*2,bias=False)，权重 [2,4]，8 个参数。
        v_proj=Linear(4,1*2,bias=False)，权重 [2,4]，8 个参数。
        各自将输入 [1,2,4] -> [1,2,2] -> 拆头 [1,2,1,2]。
        K 用于与 Q 打分，V 提供被加权汇总的内容；两者参数独立。

    5. 创建输出投影
        o_proj=Linear(2*2,4,bias=False)，权重 [4,4]，16 个参数。
        多头结果合并成 [1,2,4]，再由它映射到隐藏宽度 4。

    6. 创建 Q/K 各自的 RMSNorm
        q_norm.weight=[1,1]，k_norm.weight=[1,1]。
        各有 2 个可训练参数，在各头的最后一维归一化。
        两个归一化模块不共享 weight；它们也不等同于 Block 中 H 维的归一化。

    7. 创建两个 Dropout 并保存概率
        attn_dropout=Dropout(0.0)
        resid_dropout=Dropout(0.0)
        self.dropout=0.0
        本例概率为 0，因此不会随机丢弃任何元素。

    8. 判断是否允许调用 SDPA
        cfg.flash_attn=False，因此 self.flash=False。
        后续 forward 会走显式 scores -> mask -> softmax -> 乘 V 的路径。
        设置 True 只允许使用 SDPA 接口，实际内核还取决于运行环境与输入。

    9. 构造完成
        总可训练参数数=16+8+8+16+2+2=52。
        还没有进行任何输入计算，__init__ 隐式返回 None。
        若 cfg.num_key_value_heads=None，则 KV 头数变为 2，n_rep=1，不再共享 KV 头。

    数据流：cfg -> 头数/单头宽度 -> 四个投影 -> 两个归一化 -> Dropout 与执行路径标记。
    '''
    def __init__(self, config: MiniMindConfig):
        # 初始化 Module，后续赋值的各个层会自动注册为子模块。
        super().__init__()
        # 显式配置 None 表示 KV 头数跟 Query 一样；否则使用配置中的 KV 头数。
        self.num_key_value_heads = config.num_attention_heads if config.num_key_value_heads is None else config.num_key_value_heads
        # 保存 Query 头数；local 是变量名，本文件没有在这里把头分配给多张卡。
        self.n_local_heads = config.num_attention_heads
        # 保存本模块使用的 KV 头数。
        self.n_local_kv_heads = self.num_key_value_heads
        # 每个 KV 头要供几个 Query 头使用；例如 8//4=2，需要头数整除。
        self.n_rep = self.n_local_heads // self.n_local_kv_heads
        # 单头特征宽度，决定缩放因子 sqrt(D) 和 RoPE 的维度。
        self.head_dim = config.head_dim
        # 因果注意力：位置 t 能看自己和过去，不能看未来。
        self.is_causal = True
        # 将每个 token 的 H 维投影成 Nq*D 个 Query 特征；bias=False 表示不再加偏置向量。
        self.q_proj = nn.Linear(config.hidden_size, config.num_attention_heads * self.head_dim, bias=False)
        # Key 只需 Nkv*D 维，减少投影参数和缓存中的头数。
        self.k_proj = nn.Linear(config.hidden_size, self.num_key_value_heads * self.head_dim, bias=False)
        # Value 同样只生成 Nkv*D 维；Key 用来打分，Value 是随后加权汇总的内容。
        self.v_proj = nn.Linear(config.hidden_size, self.num_key_value_heads * self.head_dim, bias=False)
        # 将拼接后的 Nq 个头映射回 H 维，方便接后续残差连接。
        self.o_proj = nn.Linear(config.num_attention_heads * self.head_dim, config.hidden_size, bias=False)
        # 为 Query 的每个头配置 RMSNorm，稳定后续点积的数值尺度。
        self.q_norm = RMSNorm(self.head_dim, eps=config.rms_norm_eps)
        # Key 采用独立的归一化权重；与 q_norm 不共享参数。
        self.k_norm = RMSNorm(self.head_dim, eps=config.rms_norm_eps)
        # 手动注意力路径中，对 softmax 后的注意力权重应用 Dropout。
        self.attn_dropout = nn.Dropout(config.dropout)
        # 对注意力输出投影后的特征应用 Dropout，然后才交回 Block 做残差相加。
        self.resid_dropout = nn.Dropout(config.dropout)
        # 单独保存概率，供无需创建 Dropout 层的 SDPA 接口使用。
        self.dropout = config.dropout
        # 接口存在且配置允许才启用 SDPA 候选路径；属性名 flash 不代表一定使用 FlashAttention 内核。FlashAttention 是一种针对深度学习中 Transformer 架构的自注意力机制Self-Attention） 的加速算法。
        self.flash = hasattr(torch.nn.functional, 'scaled_dot_product_attention') and config.flash_attn

    '''
    【完整例子：两个 token、两个 Query 头，逐步计算注意力和缓存】

    假设按 Attention.__init__ 的例子建立 H=4、Nq=2、Nkv=1、D=2 的模块：
        dropout=0，flash_attn=False，rms_norm_eps=0.000001
        x=[[[1,2,3,4],[5,6,7,8]]]，FP32，形状 [1,2,4]
        past_key_value=None，use_cache=True，attention_mask=[[1,1]]
    为了手算，用 no_grad 下的 copy_/zero_ 等操作把本例参数固定为：
        q_proj.weight = 4×4 全零矩阵
        k_proj.weight = 2×4 全零矩阵
        v_proj.weight = [[1,0,0,0],[0,1,0,0]]
        o_proj.weight = 4×4 单位矩阵
        q_norm.weight = k_norm.weight = [1,1]
    这是刻意构造的教学参数，不是默认随机初始化结果；Q/K 全零让 softmax 方便手算。
    位置表取 precompute_freqs_cis(dim=2,end=2) 的结果：
        cos=[[1,1],[0.540302,0.540302]]
        sin=[[0,0],[0.841471,0.841471]]

    1. 解包 x.shape
        bsz=1，seq_len=2，隐藏宽度=4。

    2. 三个线性投影（Linear 计算 x @ weight.T）
        xq=[[[0,0,0,0],[0,0,0,0]]]，形状 [1,2,4]
        xk=[[[0,0],[0,0]]]，形状 [1,2,2]
        xv=[[[1,2],[5,6]]]，形状 [1,2,2]
        Value 投影只取输入的前两个特征。

    3. view 拆头
        Q:[1,2,2,2]，每个位置的两个头均为 [0,0]。
        K:[1,2,1,2]，每个位置只有一个 [0,0] 头。
        V:[1,2,1,2]，位置 0 的头为 [1,2]，位置 1 的头为 [5,6]。

    4. Q/K 归一化，再应用 RoPE
        零向量的归一化分母是 sqrt(eps)>0，归一化后仍为 [0,0]。
        零向量乘 cos、sin 后仍为 [0,0]；因此本例旋转后的 Q/K 仍全零。
        非零向量的逐特征旋转过程见 apply_rotary_pos_emb 的完整数值例子。

    5. 处理缓存
        没有历史缓存，不拼接。
        use_cache=True，先保存：
            K_cache=[[[[0,0]],[[0,0]]]]，形状 [1,2,1,2]
            V_cache=[[[[1,2]],[[5,6]]]]，形状 [1,2,1,2]
        保存时还没有复制 KV 头，所以缓存只保留一个 KV 头。

    6. repeat_kv 后 transpose
        Q 变为 [1,2,2,2]，轴顺序现在是 [B,头,位置,D]。
        K/V 从 1 个头展开为 2 个头，也变成 [1,2,2,2]。
        两个 V 头的内容相同，每个头都是：
            [[1,2],
             [5,6]]
        注意本例尺寸巧合地相同，但 transpose 前后的“轴含义”已经不同。

    7. 计算 scores=(Q @ K.T)/sqrt(2)
        每个头得到 [[0,0],[0,0]]，完整形状 [1,2,2,2]。

    8. 添加因果屏蔽
        full((2,2),-inf).triu(1) 得到：
            [[0,-inf],
             [0,   0]]
        无缓存时最后 seq_len=2 列就是全部列，相加后的每头分数为同一矩阵。
        attention_mask=[[1,1]] 展开为 [1,1,1,2]，额外偏置为 [0,0]，不再改变分数。

    9. softmax 后乘 V
        每个头的概率：
            [[1,0],
             [0.5,0.5]]
        第 0 个 Query：1*[1,2]+0*[5,6]=[1,2]。
        第 1 个 Query：0.5*[1,2]+0.5*[5,6]=[3,4]。
        Dropout 概率为 0，结果保持不变。

    10. 转置、合并头、输出投影
        两个头拼起来：
            [[[1,2,1,2],
              [3,4,3,4]]]，形状 [1,2,4]
        o_proj 是单位矩阵，resid_dropout 为 0，数值不变。

    11. 最终返回
        output=[[[1,2,1,2],[3,4,3,4]]]
        past_kv=(K_cache,V_cache)
        不是把注意力输出当缓存；缓存保存的是 K 和 V。

    【再完整走一轮缓存解码】
    输入新 token x=[[[9,10,11,12]]]，形状 [1,1,4]，传入上面的 past_kv：
        position_embeddings 取位置 2，attention_mask=[[1,1,1]]，use_cache=True。

    1. 新 Q/K 仍为零，新 V=[9,10]。
    2. 沿位置轴拼接，K/V 缓存都变为 [1,3,1,2]，V 依次为 [1,2]、[5,6]、[9,10]。
    3. 展开 KV 头后，Q:[1,2,1,2]，K/V:[1,2,3,2]。
    4. 分数每头为 [[0,0,0]]，形状 [1,2,1,3]。
    5. 只在最后 1 列加 1×1 的因果矩阵 [[0]]，历史两列完全可见。
    6. softmax=[[1/3,1/3,1/3]]，加权 V 得 [(1+5+9)/3,(2+6+10)/3]=[5,6]。
    7. 合并头并投影，返回 output=[[[5,6,5,6]]] 和长度为 3 的新缓存。

    其它分支：
        首次两个 token 的 attention_mask 若改为 [[1,0]]，第二列被压低，
        第 1 个 Query 也只能汇总第一个 V，因此输出第二行变为 [1,2,1,2]。
        mask 屏蔽的是 Key 列，不会直接把该位置的 Query 输出置零。
        use_cache=False 时第二个返回值为 None；已有缓存仍可作为输入参与计算。
        开启 SDPA 且满足分支条件时，其目标计算相同；单 token 解码仍走显式路径。

    数据流：x -> Q/K/V -> 拆头 -> Q/K 归一化与旋转 -> 拼历史 -> 存缓存 -> 复制 KV 头
            -> QK 点积 -> 屏蔽 -> softmax -> 加权 V -> 合并头 -> 输出投影。
    '''
    def forward(self, x, position_embeddings, past_key_value=None, use_cache=False, attention_mask=None):
        # 取批大小和本次长度；_ 接收但不继续使用隐藏维度 H。
        bsz, seq_len, _ = x.shape
        # 三个线性投影分别产生 Q:[B,T,Nq*D]、K/V:[B,T,Nkv*D]。
        xq, xk, xv = self.q_proj(x), self.k_proj(x), self.v_proj(x)
        # 把 Query 最后一维拆成“头数、每头宽度”，得到 [B,T,Nq,D]。
        xq = xq.view(bsz, seq_len, self.n_local_heads, self.head_dim)
        # Key 同样拆头，但头数为 Nkv，得到 [B,T,Nkv,D]。
        xk = xk.view(bsz, seq_len, self.n_local_kv_heads, self.head_dim)
        # Value 使用与 Key 一样的布局，便于之后按位置拼接缓存。
        xv = xv.view(bsz, seq_len, self.n_local_kv_heads, self.head_dim)
        # 分别对 Q/K 的最后 D 维归一化，不改变形状。
        xq, xk = self.q_norm(xq), self.k_norm(xk)
        # 取出已按本次位置范围切好的 cos/sin，各为 [T,D]。
        cos, sin = position_embeddings
        # 只旋转本次新算的 Q/K；历史 K 在产生缓存时已经旋转过，不应再旋转。
        xq, xk = apply_rotary_pos_emb(xq, xk, cos, sin)
        # 如果存在历史缓存，就把当前 K/V 接到历史的序列维后面。
        if past_key_value is not None:
            # past_key_value[0] 为历史 K；dim=1 是 token 位置轴，拼后长度为 S。
            xk = torch.cat([past_key_value[0], xk], dim=1)
            # past_key_value[1] 为历史 V，以同样顺序拼接，保证 K 和 V 的位置一一对应。
            xv = torch.cat([past_key_value[1], xv], dim=1)
        # 按开关保存尚未扩展 KV 头的张量；False 仅影响是否返回缓存，已有缓存仍会参与上面的计算。
        past_kv = (xk, xv) if use_cache else None
        # 将头放到序列前，Q 得 [B,Nq,T,D]；K/V 先重复头，再得到 [B,Nq,S,D]。
        xq, xk, xv = (xq.transpose(1, 2), repeat_kv(xk, self.n_rep).transpose(1, 2), repeat_kv(xv, self.n_rep).transpose(1, 2))
        # SDPA 路径要求 T>1、因果模式下无历史缓存，且没有需屏蔽的 padding；否则走下面的显式计算。
        if self.flash and (seq_len > 1) and (not self.is_causal or past_key_value is None) and (attention_mask is None or torch.all(attention_mask == 1)):
            # 接口内部完成缩放点积、因果屏蔽、softmax 和乘 V；评估时必须显式把其 dropout_p 设为 0。
            output = F.scaled_dot_product_attention(xq, xk, xv, dropout_p=self.dropout if self.training else 0.0, is_causal=self.is_causal)
        # 单 token 解码、存在缓存或 padding 等情况，使用下面的手动注意力路径。
        else:
            # K 的最后两轴交换后为 [B,Nq,D,S]；矩阵乘得 [B,Nq,T,S]，除 sqrt(D) 控制分数量级。
            scores = (xq @ xk.transpose(-2, -1)) / math.sqrt(self.head_dim)
            # 最后 T 列属于本次新 token：给其中的严格上三角加 -inf；历史列全可见，不加这个三角屏蔽。
            if self.is_causal: scores[:, :, :, -seq_len:] += torch.full((seq_len, seq_len), float("-inf"), device=scores.device).triu(1)
            # mask:[B,S] → [B,1,1,S]；1 变 0 不影响分数，0 变 -1e9 压低对应 Key 的分数。
            if attention_mask is not None: scores += (1.0 - attention_mask.unsqueeze(1).unsqueeze(2)) * -1e9
            # FP32 softmax 沿 S 维得概率，转回 Q 的 dtype；Dropout 后乘 V，输出 [B,Nq,T,D]。
            output = self.attn_dropout(F.softmax(scores.float(), dim=-1).type_as(xq)) @ xv
        # 交换回 [B,T,Nq,D]，reshape 合并头与特征；-1 自动推断为 Nq*D，必要时会复制内存。
        output = output.transpose(1, 2).reshape(bsz, seq_len, -1)
        # o_proj 映射回 [B,T,H]，再做残差分支上的 Dropout。
        output = self.resid_dropout(self.o_proj(output))
        # 返回本次的输出，以及 (K,V) 或 None；残差相加由外层 Block 完成。
        return output, past_kv


# 普通前馈网络逐 token 处理特征，不在不同位置之间交换信息；默认激活为 SiLU，构成 SwiGLU 形式。
class FeedForward(nn.Module):
    '''
    【完整例子：创建一个 2→3→2 的门控前馈网络】

    假设：
        cfg=MiniMindConfig(hidden_size=2,intermediate_size=3,hidden_act='silu')
        ffn=FeedForward(cfg)

    1. super().__init__() 初始化模块。
    2. intermediate_size 参数没有传入，值为 None。
        intermediate_size or config.intermediate_size -> None or 3 -> 3。
        如果调用 FeedForward(cfg,intermediate_size=4)，本层改用 4，但不会修改 cfg 中的 3。
        因为使用 or，显式传 0 也会回退到配置值；有效宽度应为正整数。
    3. gate_proj=Linear(2,3,bias=False)，权重形状 [3,2]，6 个参数。
    4. down_proj=Linear(3,2,bias=False)，权重形状 [2,3]，6 个参数。
    5. up_proj=Linear(2,3,bias=False)，权重形状 [3,2]，6 个参数。
    6. ACT2FN['silu'] 找到 SiLU 激活函数，其标量公式为 a/(1+exp(-a))。
    7. 最终得到 ffn，共 18 个可训练权重，没有偏置。
        gate_proj 与 up_proj 是两份独立参数，不是同一个线性层调用两次。
        这里 gate 的输出是特征调节量，不是 MoE 的专家选择概率。

    后续输入 [[[1,2]]]，形状 [1,1,2] 时：
        gate_proj -> [1,1,3] -> SiLU
        up_proj   -> [1,1,3]
        两条分支逐元素相乘 -> [1,1,3]
        down_proj -> [1,1,2]
    构造函数只创建这些部件，隐式返回 None；具体数值计算见下面 forward 的例子。

    数据流：配置 H=2、I=3 -> 两份 [3,2] 权重与一份 [2,3] 权重 -> 可调用的 ffn。
    '''
    def __init__(self, config: MiniMindConfig, intermediate_size: int = None):
        # 初始化父类，使三个线性层能够注册为子模块。
        super().__init__()
        # 优先使用传入的中间宽度；or 会让 None 或 0 都回退到配置值，因此有效宽度应为正数。
        intermediate_size = intermediate_size or config.intermediate_size
        # 门控分支：H→I，之后通过激活函数得到逐特征的调节量。
        self.gate_proj = nn.Linear(config.hidden_size, intermediate_size, bias=False)
        # 输出分支：I→H，使输出宽度与输入一致，能与残差相加。
        self.down_proj = nn.Linear(intermediate_size, config.hidden_size, bias=False)
        # 内容分支：独立的 H→I 投影，提供被门控调节的特征。
        self.up_proj = nn.Linear(config.hidden_size, intermediate_size, bias=False)
        # 按字符串查找实际激活函数；默认是 SiLU，若名字不在映射表中则会报错。
        self.act_fn = ACT2FN[config.hidden_act]

    '''
    【完整例子：给出全部权重，手算两条分支及最终输出】

    假设 H=2、I=3、激活函数为 SiLU，输入：
        x=torch.tensor([[[1.,2.]]])，形状 [1,1,2]
    将本例的三个权重固定为：
        gate_proj.weight=[[1,0],[0,1],[1,1]]
        up_proj.weight  =[[2,0],[0,3],[1,-1]]
        down_proj.weight=[[1,0,1],[0,1,1]]
    这些数值由教学例子指定，不是随机初始化一定会产生的值。

    1. self.gate_proj(x)
        Linear 用 x @ weight.T，逐行做点积：
            第 0 项=1*1+2*0=1
            第 1 项=1*0+2*1=2
            第 2 项=1*1+2*1=3
        得到 gate=[[[1,2,3]]]，形状 [1,1,3]。

    2. self.act_fn(gate)
        SiLU(1)=1/(1+exp(-1))≈0.731059
        SiLU(2)=2/(1+exp(-2))≈1.761594
        SiLU(3)=3/(1+exp(-3))≈2.857722
        得到 [[[0.731059,1.761594,2.857722]]]。

    3. self.up_proj(x)
        第 0 项=1*2+2*0=2
        第 1 项=1*0+2*3=6
        第 2 项=1*1+2*(-1)=-1
        得到 up=[[[2,6,-1]]]，形状 [1,1,3]。

    4. 两条分支逐元素相乘
        [0.731059*2,1.761594*6,2.857722*(-1)]
        ≈ [1.462117,10.569565,-2.857722]
        这是三个特征各自相乘，不是求点积，仍保留 3 个数。

    5. self.down_proj(...)
        第 0 个输出=1.462117*1+10.569565*0+(-2.857722)*1
                    ≈ -1.395605
        第 1 个输出=1.462117*0+10.569565*1+(-2.857722)*1
                    ≈ 7.711843

    6. 最终返回
        [[[-1.395605,7.711843]]]，形状 [1,1,2]。
        本函数没有加回原始 x；残差连接由外面的 MiniMindBlock 完成。
        若输入有多个 token，这套运算逐 token 独立进行，权重在它们之间共享。
        MoE 传入二维 [N,H] 时，同一计算也成立。

    数据流：[1,2] -> gate=[1,2,3] -> SiLU
                  -> up=[2,6,-1] -> 两路相乘 -> down 投影 -> [-1.395605,7.711843]。
    '''
    def forward(self, x):
        # 先分别做 gate/up 投影，只激活 gate，再相乘，最后 down 投影；此函数自身不做残差相加。
        return self.down_proj(self.act_fn(self.gate_proj(x)) * self.up_proj(x))


# MoE 为每个 token 选择少数几个独立前馈专家，将它们的输出按路由权重相加。
class MOEFeedForward(nn.Module):
    '''
    【完整例子：创建一个路由器和三个独立专家】

    假设：
        cfg=MiniMindConfig(hidden_size=2,use_moe=True,
                           num_experts=3,num_experts_per_tok=2,
                           moe_intermediate_size=2,hidden_act='silu',
                           norm_topk_prob=True,router_aux_loss_coef=0.0005)
        moe=MOEFeedForward(cfg)

    1. super().__init__() 初始化 Module，然后 self.config=cfg 保存同一个配置对象。
    2. gate=Linear(2,3,bias=False)
        gate.weight.shape=[3,2]，共有 6 个参数。
        输入一行 [x0,x1]，输出三个专家分数；此时没有 softmax，也还没有选择专家。
    3. range(config.num_experts)=range(3)，依次生成专家 0、1、2。
        每次执行 FeedForward(cfg,intermediate_size=2)，创建一个新的实例。
        每个专家都有：
            gate_proj.weight:[2,2]
            up_proj.weight:[2,2]
            down_proj.weight:[2,2]
        每个专家共 12 个参数，三个专家共 36 个；它们互不共享权重。
    4. ModuleList([专家0,专家1,专家2]) 注册这些子模块。
        因而 model.parameters()、state_dict()、to(device) 都能找到它们。
        专家列表本身不负责路由，forward 会明确循环访问各个专家。
    5. self.act_fn=ACT2FN['silu']
        当前 MoE.forward 不直接调用该属性；专家内部使用自己的 act_fn。
    6. 构造完成，总可训练参数数=路由器6+专家36=42。
        __init__ 隐式返回 None；本次还没有 aux_loss，它在 forward 时才被设置。

    后续输入两个 token，形状 [1,2,2]：
        展平 [2,2] -> gate 分数 [2,3] -> 每行选择 2 个专家 -> 汇总回 [1,2,2]。
        token0 可以选专家 0/1，token1 可以选专家 2/1；
        num_experts_per_tok=2 限制的是每个 token，不是限制整个批次只能使用两个专家。

    数据流：cfg -> [3,2] 路由权重 + 3 套独立的 2→2→2 专家 -> moe 对象。
    '''
    def __init__(self, config: MiniMindConfig):
        # 初始化 Module，准备注册路由器和专家列表。
        super().__init__()
        # 保存配置，以便 forward 读取 K、是否重新归一化、辅助损失系数等。
        self.config = config
        # 路由器将每个 token 的 H 维表示映射成 E 个未归一化的专家分数。
        self.gate = nn.Linear(config.hidden_size, config.num_experts, bias=False)
        # 创建 E 个不同的前馈实例；ModuleList 保证专家参数会随模型保存、迁移设备并被优化器发现。
        self.experts = nn.ModuleList([FeedForward(config, intermediate_size=config.moe_intermediate_size) for _ in range(config.num_experts)])
        # 保存激活函数引用；当前 MoE.forward 不直接调用它，真正的激活在每个专家内部执行。
        self.act_fn = ACT2FN[config.hidden_act]

    '''
    【完整例子：两个 token 分发到三个专家，再逐项加回输出】

    假设：
        B=1，T=2，H=2，E=3，K=2
        x=torch.tensor([[[1.,0.],[0.,1.]]])
        norm_topk_prob=True，router_aux_loss_coef=0.0005，处于训练模式。

    为使整个例子可以复算，固定路由器：
        gate.weight=[
            [log(0.6),log(0.2)],
            [log(0.3),log(0.3)],
            [log(0.1),log(0.5)]
        ]
    专家也固定为可实现以下结果的权重：
        a=SiLU(1)≈0.731059
        每个专家 gate_proj.weight 和 up_proj.weight 都是 2×2 单位矩阵。
        专家0 down_proj.weight=[[2/a,0],[0,0]]
        专家1 down_proj.weight=[[0,0],[3/a,8/a]]
        专家2 down_proj.weight=[[0,4/a],[0,0]]
    例如输入 [1,0] 时，两条分支相乘得到 [a,0]，再乘专家0的输出矩阵就得到 [2,0]。
    因此这些输出来自具体权重，而不是没有定义来源的假定结果。

    1. 解包形状，再 x.view(-1,hidden_dim)
        batch_size=1，seq_len=2，hidden_dim=2
        x_flat=[[1,0],[0,1]]，形状 [2,2]。
        第 0 行叫 token0，第 1 行叫 token1。

    2. gate(x_flat) 再 softmax
        第 0 行分数为 [log(0.6),log(0.3),log(0.1)]。
        第 1 行分数为 [log(0.2),log(0.3),log(0.5)]。
        每行指数之和都为 1，因此：
            scores=[[0.6,0.3,0.1],
                    [0.2,0.3,0.5]]，形状 [2,3]。

    3. topk 选两个专家
        为展示索引，按本次得到的槽位顺序写成：
            topk_idx   =[[0,1],[2,1]]
            topk_weight=[[0.6,0.3],[0.5,0.3]]
        sorted=False 不承诺槽位顺序；即使每行两项交换，只要编号与权重对应，最终汇总结果相同。

    4. 对选中权重重新归一化
        每行的和为 [[0.9],[0.8]]，加很小的 1e-20 后相除：
            topk_weight≈[[2/3,1/3],[0.625,0.375]]
        它们在每行各自加起来约为 1。

    5. 初始化 y=zeros_like(x_flat)
        y=[[0,0],[0,0]]，用于累加，不是覆盖原输入。

    6. 循环到专家 0
        mask=(topk_idx==0)：
            [[True,False],
             [False,False]]
        mask.any(-1)=[True,False]
        nonzero().flatten() -> token_idx=[0]
        topk_weight[mask].view(-1,1) -> weight=[[2/3]]
        expert0(x_flat[[0]]) -> [[2,0]]
        乘权重 -> [[4/3,0]]
        y.index_add_(0,[0],...) 后：
            y=[[4/3,0],[0,0]]

    7. 循环到专家 1
        mask=[[False,True],[False,True]]
        token_idx=[0,1]
        weight=[[1/3],[0.375]]
        expert1(x_flat[[0,1]])=[[0,3],[0,8]]
        乘权重 -> [[0,1],[0,3]]
        分别加回第 0/1 行：
            y=[[4/3,1],[0,3]]

    8. 循环到专家 2
        mask=[[False,False],[True,False]]
        token_idx=[1]
        weight=[[0.625]]
        expert2(x_flat[[1]])=[[4,0]]
        乘权重 -> [[2.5,0]]
        加回第 1 行：
            y=[[4/3,1],[2.5,3]]

    9. 计算训练辅助损失
        one_hot(topk_idx,3) 得到形状 [2,2,3]：
            token0：[[1,0,0],[0,1,0]]
            token1：[[0,0,1],[0,1,0]]
        沿 token 轴 mean(0)：
            load=[[0.5,0,0.5],[0,1,0]]，形状 [2,3]
        scores.mean(0)=[0.4,0.3,0.3]，形状 [3]，广播到两个槽位。
        相乘：
            [[0.2,0,0.15],[0,0.3,0]]
        sum()=0.65
        aux_loss=0.65*3*0.0005=0.000975
        保存到 self.aux_loss，不在这里直接加到 y 上。
        本实现把 K 个槽位求和，没有额外除以 K。

    10. y.view(1,2,2)，最终返回
        [[[1.333333,1.0],[2.5,3.0]]]
        辅助损失通过 moe.aux_loss 读取，随后由外层模型累加各层损失。

    【其它分支也用本例检查】
        norm_topk_prob=False：
            token0=0.6*[2,0]+0.3*[0,3]=[1.2,0.9]
            token1=0.5*[4,0]+0.3*[0,8]=[2.0,2.4]
            输出改为 [[[1.2,0.9],[2.0,2.4]]]。
        改用 eval()：路由和加权输出不变，self.aux_loss=标量张量0。
        若批次只保留 token0，它只选专家0/1：
            专家2的 mask 全 False，训练时执行 0*sum(专家2参数)，对 y 的数值贡献为0，
            但这些参数仍与结果的计算图相连；评估时直接跳过这个零贡献分支。

    数据流：x -> 展平 -> 路由概率 -> top-k -> 归一化 -> 按专家找 token -> 加权累加
            -> 计算辅助损失 -> 恢复 [B,T,H]。
    '''
    def forward(self, x):
        # 保存原来的三维形状，以便最后把展平后的 token 还原回各条序列。
        batch_size, seq_len, hidden_dim = x.shape
        # 合并 batch 和时间轴；N=B*T，每行对应原来的一个 token，最后一维 H 不变。
        x_flat = x.view(-1, hidden_dim)
        # gate 得到 [N,E] 分数，再沿专家维 softmax，让每行 E 个概率之和为 1。
        scores = F.softmax(self.gate(x_flat), dim=-1)
        # 对每行选 K 个最大概率，同时返回权重 [N,K] 和专家编号 [N,K]；不要求这 K 项内部排序。
        topk_weight, topk_idx = torch.topk(scores, k=self.config.num_experts_per_tok, dim=-1, sorted=False)
        # 用选中概率的总和归一化；keepdim 保留 [N,1] 以便广播，1e-20 是分母稳定项。
        if self.config.norm_topk_prob: topk_weight = topk_weight / (topk_weight.sum(dim=-1, keepdim=True) + 1e-20)
        # 建立 [N,H] 的全零结果，dtype/device 跟输入一致，后续不断累加各专家贡献。
        y = torch.zeros_like(x_flat)
        # enumerate 同时给出专家编号 i 和对应的 FeedForward 实例。
        for i, expert in enumerate(self.experts):
            # 得到 [N,K] 布尔表；True 表示某 token 的某个 top-k 槽位选中了当前专家。
            mask = (topk_idx == i)
            # 只要至少有一个 token 选中了该专家，就实际执行该专家的前馈计算。
            if mask.any():
                # any(-1) 合并槽位，nonzero 找出被选 token 的行号，flatten 将 [M,1] 变为 [M]。
                token_idx = mask.any(dim=-1).nonzero().flatten()
                # 按相同布尔表提取路由权重，转成 [M,1]，以便乘到专家输出的全部 H 个特征上。
                weight = topk_weight[mask].view(-1, 1)
                # 取 M 个 token 交给专家，乘各自权重并转回 y 的 dtype；index_add_ 沿第 0 轴原地累加。
                y.index_add_(0, token_idx, (expert(x_flat[token_idx]) * weight).to(y.dtype))
            # 没有 token 使用当前专家，但模型处于训练模式时，仍保留它与结果的计算图连接。
            elif self.training:
                # 专家全部参数求和再乘 0，数值贡献为零，但参数仍出现在图中；有助于处理分布式未使用参数。
                y[0, 0] += 0 * sum(p.sum() for p in expert.parameters())
        # 仅在训练且系数为正时计算均衡目标；专家选择离散，但平均路由概率仍保留梯度路径。
        if self.training and self.config.router_aux_loss_coef > 0:
            # one_hot:[N,K,E]；float 后沿 N 求均值，得到 [K,E]，记录各槽位对各专家的选择比例。
            load = F.one_hot(topk_idx, self.config.num_experts).float().mean(0)
            # [E] 的平均概率广播到 [K,E]，相乘求和，再乘专家数和系数；保存在属性供模型层汇总。
            self.aux_loss = (load * scores.mean(0)).sum() * self.config.num_experts * self.config.router_aux_loss_coef
        # 评估模式或系数不为正时，不为本次前向增加路由辅助损失。
        else:
            # new_zeros 跟随 scores 的设备和 dtype；squeeze 把长度为 1 的向量变成零维标量张量。
            self.aux_loss = scores.new_zeros(1).squeeze()
        # 将 N 个 token 恢复为 [B,T,H]；辅助损失放在属性里，不作为这个函数的第二个返回值。
        return y.view(batch_size, seq_len, hidden_dim)


# 一个 Block 先做注意力，再做前馈；每个子层前先归一化，并在子层输出上加回原输入。
class MiniMindBlock(nn.Module):
    '''
    【完整例子：组装一层完整 Transformer Block】

    假设：
        cfg=MiniMindConfig(hidden_size=2,num_attention_heads=1,
                           num_key_value_heads=1,head_dim=2,
                           intermediate_size=2,use_moe=False,
                           dropout=0.0,flash_attn=False)
        block=MiniMindBlock(layer_id=0,config=cfg)

    1. super().__init__() 初始化 Module。
    2. self.self_attn=Attention(cfg)
        Q/K/V/O 投影权重均为 [2,2]，各有 4 个参数；
        q_norm/k_norm 权重各为 [2]，共 4 个参数；
        注意力模块合计 20 个参数。
    3. self.input_layernorm=RMSNorm(2,eps=cfg.rms_norm_eps)
        权重初始 [1,1]，在注意力之前处理每个 token。
    4. self.post_attention_layernorm=RMSNorm(2,eps=cfg.rms_norm_eps)
        另一组独立的 [1,1]，处理注意力残差相加后的表示。
        两个 norm 共 4 个参数，不共享权重。
    5. 因为 cfg.use_moe=False：
        self.mlp=FeedForward(cfg)
        三个投影矩阵均为 [2,2]，共 12 个参数。
    6. 构造结束
        本 Block 合计 20+4+12=36 个可训练参数。
        __init__ 隐式返回 None，后续 block(...) 才处理输入。
        layer_id=0 虽然传入了，但当前实现没有保存或使用该编号。

    如果用相同宽度，改成 use_moe=True、num_experts=3、num_experts_per_tok=2：
        self.mlp 会是 MOEFeedForward；
        路由器 6 个参数，三个专家各 12 个，共 42 个；
        Block 总参数数=20+4+42=66。
        其它注意力和残差结构不变，输入输出形状仍为 [B,T,2]。

    数据流：cfg -> 注意力 + 前归一化 + 后注意力归一化 + 普通前馈或MoE -> block。
    '''
    def __init__(self, layer_id: int, config: MiniMindConfig):
        # 初始化模块管理机制，方便注册下面四个子模块。
        super().__init__()
        # 本层的自注意力模块，负责在可见 token 之间交换信息。
        self.self_attn = Attention(config)
        # 注意力之前，按每个 token 的 H 个特征做 RMSNorm。
        self.input_layernorm = RMSNorm(config.hidden_size, eps=config.rms_norm_eps)
        # 注意力残差相加之后、前馈之前，使用另一套 RMSNorm 参数。
        self.post_attention_layernorm = RMSNorm(config.hidden_size, eps=config.rms_norm_eps)
        # 条件表达式选择普通前馈或 MoE，二者均保证输出形状等于输入形状。
        self.mlp = FeedForward(config) if not config.use_moe else MOEFeedForward(config)

    '''
    【完整例子：从两个输入向量算出两次残差相加的结果】

    假设使用上一例的 H=2、Nq=Nkv=1、D=2、I=2 普通前馈 Block：
        hidden_states=[[[1.,0.],[0.,1.]]]，形状 [1,2,2]
        use_cache=True，past_key_value=None，attention_mask=[[1,1]]
        dropout=0，eps=0.000001
    固定参数：
        注意力 Q/K 投影全为0，V/O投影为2×2单位矩阵；
        所有 RMSNorm.weight=[1,1]；
        前馈 gate/up/down 的权重均为2×2单位矩阵；
        位置表取位置0、1。
    以下数值忽略很小 eps 并保留约六位小数；真实代码结果仅有舍入级差别。

    1. residual=hidden_states
        residual=[[[1,0],[0,1]]]
        保存的是原输入引用；下一个注意力调用会返回新的输出张量。

    2. input_layernorm(hidden_states)
        第一行均方值=(1²+0²)/2=0.5，除 sqrt(0.5)：
            [1,0] -> [1.414214,0]
        第二行同理：
            [0,1] -> [0,1.414214]
        归一化结果记为 z，形状仍为 [1,2,2]。

    3. self.self_attn(z,...)
        Q/K投影为0，因此经过归一化和RoPE仍为0。
        V投影是单位矩阵，因此 V 的两个位置为：
            [1.414214,0]、[0,1.414214]
        因果 softmax：
            位置0权重 [1,0]
            位置1权重 [0.5,0.5]
        注意力输出：
            [[[1.414214,0],
              [0.707107,0.707107]]]
        present_key_value：
            K全0，形状[1,2,1,2]；
            V为上面的归一化输入，形状[1,2,1,2]。

    4. hidden_states += residual
        第一行：[1.414214,0]+[1,0]=[2.414214,0]
        第二行：[0.707107,0.707107]+[0,1]=[0.707107,1.707107]
        第一次残差结果 h1：
            [[[2.414214,0],
              [0.707107,1.707107]]]

    5. post_attention_layernorm(h1)
        第一行归一化后=[1.414214,0]
        第二行的均方值：
            (0.707107²+1.707107²)/2≈1.707107
            平方根≈1.306563
            归一化后=[0.541196,1.306563]
        两行的归一化分母各算各的。

    6. self.mlp(...)
        三个矩阵都是单位矩阵，所以每个特征 v 的前馈输出为 SiLU(v)*v：
            1.414214 -> 1.608859
            0 -> 0
            0.541196 -> 0.185135
            1.306563 -> 1.343386
        MLP输出：
            [[[1.608859,0],
              [0.185135,1.343386]]]

    7. 第二次残差相加
        h1+MLP(norm(h1))：
            第一行=[2.414214,0]+[1.608859,0]=[4.023073,0]
            第二行=[0.707107,1.707107]+[0.185135,1.343386]
                  =[0.892242,3.050493]

    8. 最终返回
        hidden_states≈[[[4.023073,0],[0.892242,3.050493]]]
        present_key_value=(K,V)，与步骤3得到的注意力缓存相同。
        前馈阶段不会修改或新增 KV 缓存。
        use_cache=False 时第二个返回值为 None。
        换成 MoE 时，步骤6按 MOEFeedForward 的路由过程产生同形状输出，再做相同的步骤7。

    数据流：输入 -> norm -> Attention -> 加原输入 -> norm -> MLP -> 加第一次残差结果 -> 返回。
    '''
    def forward(self, hidden_states, position_embeddings, past_key_value=None, use_cache=False, attention_mask=None):
        # 保留原始输入的引用，供第一次残差相加；这里不是 clone，也没有额外复制张量。
        residual = hidden_states
        # 调用注意力，接收本次位置的输出和本层新缓存。
        hidden_states, present_key_value = self.self_attn(
            # 先归一化输入，再传入 cos/sin 位置表；属于子层计算前归一化的结构。
            self.input_layernorm(hidden_states), position_embeddings,
            # 后三个位置参数依次是历史缓存、是否返回缓存、可见位置掩码。
            past_key_value, use_cache, attention_mask
        )
        # 把注意力变换结果与原始输入逐元素相加；+= 在当前注意力输出张量上原地更新。
        hidden_states += residual
        # 将第一次相加的结果归一化后送入前馈，再与未归一化的该结果相加，形成第二条残差连接。
        hidden_states = hidden_states + self.mlp(self.post_attention_layernorm(hidden_states))
        # 返回更新后的表示和本层缓存，让外层模型继续传给下一层并收集缓存。
        return hidden_states, present_key_value


# 主干网络把 token ID 转成上下文表示；这里只输出 H 维特征，词表打分在 MiniMindForCausalLM 中完成。
class MiniMindModel(nn.Module):
    '''
    【完整例子：词向量、两层 Block 和位置表怎样创建】

    假设：
        cfg=MiniMindConfig(hidden_size=2,num_hidden_layers=2,
                           num_attention_heads=1,num_key_value_heads=1,head_dim=2,
                           intermediate_size=2,vocab_size=4,max_position_embeddings=4,
                           dropout=0.0,flash_attn=False,use_moe=False)
        backbone=MiniMindModel(cfg)

    1. super().__init__()，再保存 cfg。
        self.vocab_size=4
        self.num_hidden_layers=2
    2. nn.Embedding(4,2)
        建立 embed_tokens.weight，形状 [4,2]，共8个可训练数值。
        编号范围为0..3；输入 [[1,2]] 时分别查第1、2行，得到 [1,2,2] 张量。
        构造时权重按初始化规则生成，不保证就是下面 forward 教学例子手工指定的数值。
    3. nn.Dropout(0.0)
        为词向量输出准备 Dropout；概率0不会改变输入。
    4. 列表推导式遍历 range(2)
        l=0 -> MiniMindBlock(0,cfg)
        l=1 -> MiniMindBlock(1,cfg)
        形成 self.layers=ModuleList([block0,block1])。
        每层36个参数，共72个；两层对象及权重不同。
    5. self.norm=RMSNorm(2,eps=0.000001)
        最后归一化的 weight=[1,1]，再增加2个参数。
    6. 调用 precompute_freqs_cis(dim=2,end=4,rope_base=1000000,rope_scaling=None)
        只有一种频率：1000000**(-0/2)=1。
        t=[0,1,2,3]，角度列=[[0],[1],[2],[3]]。
        拼接后的 cos≈
            [[1,1],[0.540302,0.540302],[-0.416147,-0.416147],[-0.989992,-0.989992]]
        sin≈
            [[0,0],[0.841471,0.841471],[0.909297,0.909297],[0.141120,0.141120]]
        两表形状均为 [4,2]，每表8个数。
    7. register_buffer(...,persistent=False)
        freqs_cos、freqs_sin 注册为 buffer，而不是 Parameter。
        它们随模型迁移设备，但不由优化器更新，也不保存进 state_dict。
    8. 构造结束
        模型参数数=词向量8+两个Block72+末尾归一化2=82。
        两张位置表共16个数，但不计入可训练参数。
        __init__ 隐式返回 None；这里没有词表输出头，也没有计算交叉熵。

    数据流：cfg -> [4,2]词向量表 -> 两个Block -> RMSNorm -> 两张[4,2]位置表 -> backbone。
    '''
    def __init__(self, config: MiniMindConfig):
        # 初始化 Module，让词向量、层列表和归一化都能注册。
        super().__init__()
        # 保存完整配置，后续若需要重建位置表，可以读取同一组参数。
        self.config = config
        # 将常用的词表大小与层数保存为实例属性；元组右侧两个值按顺序赋给左侧。
        self.vocab_size, self.num_hidden_layers = config.vocab_size, config.num_hidden_layers
        # 创建 [V,H] 的词向量表；输入整数 [B,T] 时输出浮点 [B,T,H]。
        self.embed_tokens = nn.Embedding(config.vocab_size, config.hidden_size)
        # 对刚查出的词向量做 Dropout，训练时按配置概率随机置零并按保留率缩放。
        self.dropout = nn.Dropout(config.dropout)
        # range 生成 0 到层数-1，逐个建立 Block；ModuleList 注册全部层，但前向顺序仍由 forward 编写。
        self.layers = nn.ModuleList([MiniMindBlock(l, config) for l in range(self.num_hidden_layers)])
        # 全部 Block 后再做一次 H 维 RMSNorm，然后交给语言模型输出头。
        self.norm = RMSNorm(config.hidden_size, eps=config.rms_norm_eps)
        # 按单头维度、表长、RoPE 基数和缩放配置生成两张完整位置表。
        freqs_cos, freqs_sin = precompute_freqs_cis(dim=config.head_dim, end=config.max_position_embeddings, rope_base=config.rope_theta, rope_scaling=config.rope_scaling)
        # 注册余弦表为非持久 buffer：可以随设备移动，但不作为参数，也不进入 state_dict。
        '''
            PyTorch 中普通 Tensor、nn.Parameter 和 register_buffer 的区别：

            1. 普通 Tensor：self.x = torch.tensor(...)
            - 只是普通的 Tensor，PyTorch 不会将其注册为模型参数或 Buffer。
            - 调用 model.cuda() 或 model.to(device) 时，不会自动移动到 GPU。
            - 如果原本在 CPU 上，仍然留在 CPU，需要手动调用 .to(device)。
            - 不会被优化器更新，也不会自动保存到 state_dict。

            2. nn.Parameter：self.weight = nn.Parameter(...)
            - PyTorch 会自动将其注册为模型的可训练参数。
            - 调用 model.cuda() 时，会自动跟随模型移动到 GPU。
            - 默认 requires_grad=True，可以参与反向传播和优化器更新。
            - 默认会保存到 state_dict。

            3. register_buffer：self.register_buffer("freqs_cos", freqs_cos)
            - 将普通 Tensor 注册为模型的 Buffer（非参数状态）。
            - 调用 model.cuda() 时，会自动跟随模型移动到 GPU。
            - 不属于可训练参数，不会被优化器更新。
            - 默认保存到 state_dict。
            - persistent=False 表示不保存到 state_dict，但仍会跟随模型移动设备。

            4. 为什么 MiniMind 的 RoPE 要使用 register_buffer？
            - freqs_cos 和 freqs_sin 是预先计算好的位置编码常量，不需要训练。
            - 如果只是 self.freqs_cos = freqs_cos，且它最初在 CPU 上，
                那么调用 model.cuda() 后，它仍然在 CPU。
            - forward() 中如果直接与 GPU Tensor 运算，通常会报设备不一致错误。
            - 如果每次调用 .to(x.device)，则可能每次都发生 CPU → GPU 数据传输。
            - 使用 register_buffer 后，model.cuda() 会提前将它们移动到 GPU，
                后续 forward() 可以直接使用，避免重复传输。

            总结：
            普通 Tensor：PyTorch 不自动管理其模型设备迁移。
            nn.Parameter：PyTorch 自动注册为模型参数，跟随模型移动到 GPU，可以训练。
            register_buffer：PyTorch 自动注册为模型 Buffer，跟随模型移动到 GPU，但不作为参数训练。

            注意：register_buffer() 本身并不立即将 Tensor 放到 GPU，
            而是让它在调用 model.cuda() 或 model.to(device) 时自动跟随模型移动。
        '''
        self.register_buffer("freqs_cos", freqs_cos, persistent=False)
        # 正弦表以同样方式注册；两个 buffer 在 forward 中用同一段位置范围切片。
        self.register_buffer("freqs_sin", freqs_sin, persistent=False)

    '''
    【完整例子：查词向量、跑两层、收集缓存，再输出最终表示】

    假设按上例创建 H=2、两层、V=4 的主干，并把教学参数固定为：
        embed_tokens.weight=[[0,0],[1,0],[0,1],[1,1]]
        两层所有 RMSNorm.weight=[1,1]，dropout=0，eps=0.000001。
        第0层使用 MiniMindBlock.forward 完整例子中的参数：
            Q/K为0，V/O为单位矩阵，前馈gate/up/down均为单位矩阵。
        第1层：Q/K为0，V为单位矩阵，但O投影与前馈down投影全为0。
            所以第1层仍计算自己的KV，但两个残差分支输出为0，最终保持传入表示。
    输入：
        input_ids=torch.tensor([[1,2]],dtype=torch.long)
        attention_mask=[[1,1]]，past_key_values=None，use_cache=True
    以下数值忽略很小eps并按约六位小数展示。

    1. input_ids.shape -> batch_size=1、seq_length=2。
    2. past_key_values=None 没有 layers 属性，不触发清空分支。
        past_key_values or [None]*2 -> [None,None]。
    3. 第0层没有历史缓存，因此 start_pos=0。
    4. embed_tokens(input_ids)
        编号1 -> [1,0]
        编号2 -> [0,1]
        得到 [[[1,0],[0,1]]]，形状 [1,2,2]；Dropout为0，保持不变。
    5. 检查 freqs_cos[0,0]
        正常值cos(0)=1，不进入重建分支。
    6. 位置表切片 [start_pos:start_pos+seq_length]=[0:2]
        cos=[[1,1],[0.540302,0.540302]]
        sin=[[0,0],[0.841471,0.841471]]
        每层使用同一段位置表，但各层Q/K由各自参数计算。
    7. presents=[]，开始 zip(self.layers,past_key_values) 循环。
    8. 第0层收到输入 [[[1,0],[0,1]]] 和 past_key_value=None。
        按前面的 Block 逐步例子，输出：
            h0≈[[[4.023073,0],[0.892242,3.050493]]]
        第0层缓存：
            K0全0，形状[1,2,1,2]
            V0=[[[[1.414214,0]],[[0,1.414214]]]]
        presents.append((K0,V0)) -> 列表中有一层缓存。
    9. 第1层收到 h0，而不是再次收到最初的词向量。
        注意力前归一化：
            第一行≈[1.414214,0]
            第二行≈[0.397011,1.357344]
        这些值经单位V投影形成 V1，K1仍全0，均为[1,2,1,2]。
        O投影为0 -> 注意力输出全0 -> 第一次残差后仍为h0。
        前馈down投影为0 -> 前馈输出全0 -> 第二次残差后仍为h0。
        presents再追加(K1,V1)，长度变为2。
    10. self.norm(hidden_states)
        对 h0 的每行再归一化：
            hidden_states≈[[[1.414214,0],[0.397011,1.357344]]]
        输出形状[1,2,2]。
    11. 汇总aux_loss
        两层mlp都是普通FeedForward，筛选MoE层得到空列表。
        sum([],同设备标量0)=标量张量0，而不是Python整数。
    12. 最终返回
        (
            hidden_states≈[[[1.414214,0],[0.397011,1.357344]]],
            presents=[(K0,V0),(K1,V1)],
            aux_loss=tensor(0.)
        )
        hidden_states尚未投影到词表，不是token编号或概率。

    【再输入一个token，完整跟踪缓存位置】
        input_ids=[[3]]，attention_mask=[[1,1,1]]
        past_key_values=上次的presents，use_cache=True

    1. seq_length=1；第0层K缓存长度为2，因此start_pos=2。
    2. 查编号3 -> [[[1,1]]]，本次只处理这一个token。
    3. 位置表取[2:3]，而不是重新取[0:1]。
    4. 第0层的归一化输入约为[1,1]，新V为[1,1]。
       结合历史V=[1.414214,0]、[0,1.414214]，均匀注意力输出：
            [(1.414214+0+1)/3,(0+1.414214+1)/3]
            ≈[0.804738,0.804738]
       加残差 -> [1.804738,1.804738]。
       再归一化约为[1,1]，前馈输出约[0.731059,0.731059]。
       再加残差 -> [2.535797,2.535797]。
       第0层K/V缓存长度都变为3。
    5. 第1层同样追加自己的新K/V，长度变为3；两个零输出分支保持表示不变。
    6. 最终RMSNorm -> hidden_states≈[[[1,1]]]，形状[1,1,2]。
    7. 返回这个新位置的表示、两层长度为3的缓存，以及标量0辅助损失。

    其它分支：
        use_cache=False 时，presents为[None,None]，而不是None。
        若传入带layers属性的缓存对象，当前代码会将它置None，不做格式转换。
        若freqs_cos[0,0]==0，代码按cfg重建两张完整表，并搬到hidden_states的设备后再切片。
        MoE层若各自产生0.000975与0.000500辅助损失，此处相加返回0.001475。
        缓存列表长度必须等于层数；zip按较短长度停止，并不会替调用方补齐缺失层。

    数据流：编号 -> 词向量 -> 从缓存确定位置 -> 第0层 -> 第1层 -> 最终归一化
            -> 返回本次表示、逐层缓存和辅助损失。
    '''
    def forward(self, input_ids, attention_mask=None, past_key_values=None, use_cache=False, **kwargs):
        # 输入必须有 batch 和序列两个维度；batch_size 在本函数后续没有直接使用。
        batch_size, seq_length = input_ids.shape
        # 对具有 layers 属性的缓存对象清空缓存；这是现有的兼容处理，并未把这种对象转换成列表。
        if hasattr(past_key_values, 'layers'): past_key_values = None
        # None 或空列表表示没有缓存，建立与层数等长的 None 列表；已有的非空列表则原样使用。
        past_key_values = past_key_values or [None] * len(self.layers)
        # 第 0 层 Key 的第 1 维是历史 token 数；无缓存从位置 0 开始。
        start_pos = past_key_values[0][0].shape[1] if past_key_values[0] is not None else 0
        # 用整数编号查词向量，再应用 Dropout，得到 [B,T,H]。
        hidden_states = self.dropout(self.embed_tokens(input_ids))
        # 以位置 0、第 0 维 cos 是否为 0 作为重建触发标志；正常默认幅度下这里应为 cos(0)=1。
        if self.freqs_cos[0, 0] == 0:
            # 若触发检测，完全按当前配置重新计算位置表；此判断并不检查任意位置的所有损坏情况。
            freqs_cos, freqs_sin = precompute_freqs_cis(dim=self.config.head_dim, end=self.config.max_position_embeddings, rope_base=self.config.rope_theta, rope_scaling=self.config.rope_scaling)
            # 把新表移到词向量所在设备并替换现有 buffer，避免 CPU 表与 GPU 特征直接混算。
            self.freqs_cos, self.freqs_sin = freqs_cos.to(hidden_states.device), freqs_sin.to(hidden_states.device)
        # 切出本次 T 个绝对位置的 cos/sin；例如已有 3 个位置、输入 1 个，就取 [3:4]。
        position_embeddings = (self.freqs_cos[start_pos:start_pos + seq_length], self.freqs_sin[start_pos:start_pos + seq_length])
        # 用列表按层顺序收集本次新缓存。
        presents = []
        # 将每一层与它的历史缓存配对；zip 以较短者结束，因此调用方必须保证缓存列表长度正确。
        for layer, past_key_value in zip(self.layers, past_key_values):
            # 当前层处理上一层的输出，同时返回自己更新后的缓存。
            hidden_states, present = layer(
                # [B,T,H]，第一层收到词向量，后续层收到前一层的表示。
                hidden_states,
                # 每层共享同一段 [T,D] 的旋转位置表。
                position_embeddings,
                # 只给本层传它自己的 K/V，不能把其它层的缓存混进来。
                past_key_value=past_key_value,
                # 控制本层是否把新 K/V 作为返回值保留。
                use_cache=use_cache,
                # 各层使用相同的可见位置掩码，包含需要屏蔽的 padding 信息。
                attention_mask=attention_mask
            )
            # use_cache=True 时追加 (K,V)，否则追加 None；顺序与 layers 一致。
            presents.append(present)
        # 对全部层之后的表示做最后一次 RMSNorm，输出形状保持 [B,T,H]。
        hidden_states = self.norm(hidden_states)
        # 仅选择 MoE 层的 aux_loss 求和；给 sum 指定同设备标量零，使没有 MoE 时也返回张量而非整数。
        aux_loss = sum([l.mlp.aux_loss for l in self.layers if isinstance(l.mlp, MOEFeedForward)], hidden_states.new_zeros(1).squeeze())
        # 返回特征、逐层缓存列表、辅助损失；这一步尚未计算词表 logits 或交叉熵。
        return hidden_states, presents, aux_loss


# 因果语言模型在主干网络上加词表输出头，既可计算“下一个 token”的训练损失，也可循环生成文本编号。
class MiniMindForCausalLM(PreTrainedModel, GenerationMixin):
    # 告诉预训练模型框架，本模型对应的配置类是 MiniMindConfig。
    config_class = MiniMindConfig
    # 向框架声明输出头和输入词向量的共享权重关系，供权重保存/加载等流程识别。
    _tied_weights_keys = {"lm_head.weight": "model.embed_tokens.weight"}

    '''
    【完整例子：在82个参数的主干上添加词表头，并检查权重共享】

    假设配置与 MiniMindModel.__init__ 的完整例子相同：
        H=2，V=4，层数=2，Nq=Nkv=1，D=2，I=2，use_moe=False
        cfg.tie_word_embeddings=True
        model=MiniMindForCausalLM(cfg)

    1. self.config=config or MiniMindConfig()
        已传入cfg，使用该对象。
        如果没有传config，才创建默认配置；默认规模与本小例子不同。
    2. super().__init__(self.config)
        初始化PreTrainedModel，建立框架需要的配置与模型管理状态。
    3. self.model=MiniMindModel(self.config)
        创建82个参数的主干：
            词向量[4,2]：8个
            两层Block：72个
            最后RMSNorm：[2]，2个
    4. self.lm_head=Linear(2,4,bias=False)
        新建一个[4,2]权重，8个参数，负责每个位置从2个特征得到4个候选分数。
        此时词向量表和输出头暂时是两份不同参数，合计90个。
    5. 因为tie_word_embeddings=True：
        self.model.embed_tokens.weight=self.lm_head.weight
        让词向量属性改为引用输出头的同一个Parameter。
        两个属性不是“数值相同的两份复制”，而是同一个对象：
            model.model.embed_tokens.weight is model.lm_head.weight -> True
        模型中可训练的独立参数数回到82。
    6. self.post_init()
        调用当前Transformers框架的构造收尾流程，完成权重初始化等工作。
        若要使用后面例子中人为指定的矩阵，应在构造完成后再通过no_grad写入。
    7. 构造结束
        __init__隐式返回None，model对象已经可以接收input_ids。
        直接构造只创建并初始化网络，不会自动加载已训练检查点。

    用一份具体的共享权重说明两个用途：
        假设构造后将共享矩阵设为W=[[0,0],[1,0],[0,1],[1,1]]。
        输入编号2时，Embedding取W第2行 -> [0,1]。
        若某位置的隐藏向量为[2,3]，lm_head计算与W各行的点积：
            [2,3] @ W.T = [0,2,3,5]
        四个数分别给编号0、1、2、3打分。

    如果tie_word_embeddings=False：
        跳过赋值，两份[4,2]权重独立存在，总参数数90；
        后面的训练例子使用这种设置，方便单独指定输入嵌入和输出打分矩阵。

    数据流：cfg -> 主干 -> 词表投影 -> 可选共享Parameter -> 初始化收尾 -> model。
    '''
    def __init__(self, config: MiniMindConfig = None):
        # 优先使用调用方给的配置，未给配置时使用 MiniMindConfig 的默认规模。
        self.config = config or MiniMindConfig()
        # 初始化 PreTrainedModel，接入配置、参数初始化及预训练模型管理机制。
        super().__init__(self.config)
        # 主干包含词嵌入、全部 Block、最终归一化与位置表。
        self.model = MiniMindModel(self.config)
        # 输出投影 H→V；Linear 内部用隐藏向量乘 [V,H] 权重的转置，输出未经 softmax 的分数。
        self.lm_head = nn.Linear(self.config.hidden_size, self.config.vocab_size, bias=False)
        # 开启共享时，直接把输出头的 Parameter 赋给词嵌入表，使两处引用同一对象。
        if self.config.tie_word_embeddings: self.model.embed_tokens.weight = self.lm_head.weight
        # 调用框架的构造收尾钩子，执行当前 Transformers 基类定义的权重初始化等流程。
        self.post_init()

    '''
    【完整例子：从token编号到词表分数，再逐项算移位交叉熵】

    假设：
        H=2，V=4，dropout=0，eps=0.000001，tie_word_embeddings=False
        主干各层注意力O投影和前馈down投影都为0，所以残差保留词向量；
        所有RMSNorm.weight=[1,1]，其余投影取有限数值即可。
        embed_tokens.weight=[[0,0],[1,0],[0,1],[1,1]]
        输出头权重固定为：
            lm_head.weight=[
                [0,0],
                [1/sqrt(2),0],
                [0,1/sqrt(2)],
                [1/sqrt(2),1/sqrt(2)]
            ]
    输入：
        input_ids=[[1,2,3,0]]
        labels   =[[1,2,3,-100]]
        attention_mask=[[1,1,1,0]]
        past_key_values=None，use_cache=False，logits_to_keep=0
        假设0为PAD；labels中的-100表示该目标不计损失。
    以下数值忽略很小eps的影响，不代表随机模型的默认输出。

    1. self.model(...)
        查词向量后：
            [[[1,0],[0,1],[1,1],[0,0]]]
        各层两个输出分支为0，残差不改变这些向量。
        主干末尾RMSNorm：
            hidden_states≈[[[sqrt(2),0],[0,sqrt(2)],[1,1],[0,0]]]
        形状[1,4,2]；还返回每层为None的缓存列表和aux_loss=标量0。

    2. 计算slice_indices
        logits_to_keep=0是整数，slice(-0,None)=slice(0,None)。
        因而保留全部4个位置，hidden_states[:,slice_indices,:]仍为[1,4,2]。

    3. self.lm_head(...)
        每个位置与4行权重分别做点积：
            位置0：[sqrt(2),0] -> [0,1,0,1]
            位置1：[0,sqrt(2)] -> [0,0,1,1]
            位置2：[1,1]      -> [0,0.707107,0.707107,1.414214]
            位置3：[0,0]      -> [0,0,0,0]
        logits≈[[[0,1,0,1],
                 [0,0,1,1],
                 [0,0.707107,0.707107,1.414214],
                 [0,0,0,0]]]
        形状[1,4,4]，最后一维是4个候选的原始分数。

    4. loss=None，然后因为labels不为None，进入损失分支。

    5. 一位错位并contiguous()
        x=logits[...,:-1,:]，去掉最后位置：
            形状[1,3,4]，保留原来的位置0、1、2。
        y=labels[...,1:]，去掉第一个标签：
            [[2,3,-100]]，形状[1,3]。
        对应关系：
            输入[1]的最后位置 -> 预测2；
            输入[1,2]的最后位置 -> 预测3；
            输入[1,2,3]的最后位置 -> 目标-100，忽略。

    6. view展平
        x.view(-1,x.size(-1)) -> [3,4]，每行一个预测任务：
            [[0,1,0,1],
             [0,0,1,1],
             [0,0.707107,0.707107,1.414214]]
        y.view(-1) -> [2,3,-100]。
        contiguous保证这两个切片能按目标形状供view解释。

    7. 计算每个有效目标的交叉熵
        第0行：[0,1,0,1]，正确编号2的分数是0。
            分母=exp(0)+exp(1)+exp(0)+exp(1)=2+2e
            P(编号2)=1/(2+2e)≈0.134471
            loss0=-log(P)≈2.006409
        第1行：[0,0,1,1]，正确编号3的分数是1。
            P(编号3)=e/(2+2e)≈0.365529
            loss1≈1.006409
        第2行：目标是-100，整行不计入损失，也不计入平均分母。
        最终 loss=(2.006409+1.006409)/2≈1.506409。
        cross_entropy内部完成log-softmax等运算，调用前不需要自己先做softmax。

    8. 最终返回MoeCausalLMOutputWithPast
        outputs.loss≈tensor(1.506409)
        outputs.aux_loss=tensor(0.)
        outputs.logits.shape=[1,4,4]
        outputs.past_key_values=每层一个None的列表
        outputs.hidden_states.shape=[1,4,2]，是主干的最终表示张量。
        MoE辅助损失单独返回，没有在此函数中自动加进loss。

    【生成分支的完整对照】
    仍用本例权重，但输入[[1,2,3]]，不传labels，logits_to_keep=1：
        主干输出3个位置的表示：[1,3,2]。
        slice(-1,None)只取最后位置[1,1]。
        lm_head输出[[[0,0.707107,0.707107,1.414214]]]，形状[1,1,4]。
        loss保持None，hidden_states仍包含全部3个位置。
        常规训练应使用logits_to_keep=0，让完整labels与移位logits对齐。

    数据流：input_ids -> 主干hidden_states -> 选位置 -> 词表打分 -> logits左移与labels右移
            -> 展平 -> 忽略-100 -> 有效目标平均交叉熵 -> 带字段名的结果对象。
    '''
    def forward(self, input_ids, attention_mask=None, past_key_values=None, use_cache=False, logits_to_keep=0, labels=None, **kwargs):
        # 将输入、mask、缓存和开关交给主干；**kwargs 继续向下传递，当前主干未使用其中额外字段。
        hidden_states, past_key_values, aux_loss = self.model(input_ids, attention_mask, past_key_values, use_cache, **kwargs)
        # 整数 n 转成尾部切片 -n:；n=0 时 -0 就是 0，故保留全部；非整数索引按调用方原样使用。
        # 如果logits_to_keep是3，则slice_indices=slice(-3,None)，即取最后3个位置，反映在hidden_states[:,slice_indices,:]上就是[:, -3:, :]，即保留所有batch和特征，只选最后3个序列位置。
        slice_indices = slice(-logits_to_keep, None) if isinstance(logits_to_keep, int) else logits_to_keep
        # [:,索引,:] 保留所有 batch 和特征，只选序列位置；lm_head 将这些位置从 H 维映射到 V 维。
        logits = self.lm_head(hidden_states[:, slice_indices, :])
        # 没有标签的推理调用没有监督损失，以 None 表示“未计算”，不同于损失恰好为 0。
        loss = None
        # 仅当调用方提供 labels 时进入训练目标计算；不以 self.training 作为这个分支的条件。
        if labels is not None:
            # logits 去掉最后一个位置，labels 去掉第一个位置；contiguous 确保下面 view 能按扁平布局解释。
            x, y = logits[..., :-1, :].contiguous(), labels[..., 1:].contiguous()
            # 合并 batch/位置，cross_entropy 接收原始分数与整型目标，忽略 -100，默认对有效目标求平均。
            loss = F.cross_entropy(x.view(-1, x.size(-1)), y.view(-1), ignore_index=-100)
        # 用字段名包装结果；hidden_states 在这里是最终表示张量，并非每一层中间表示组成的元组。
        return MoeCausalLMOutputWithPast(loss=loss, aux_loss=aux_loss, logits=logits, past_key_values=past_key_values, hidden_states=hidden_states)

    '''
    【完整例子：逐轮生成三个token，追踪每个变量与缓存长度】

    假设：
        这是一个V=6、H=2、两层、Nkv=1、D=2的模型，输入与模型在同一设备。
        model.eval()已关闭训练态Dropout。
        input_ids=[[1,3]]，其中1表示BOS，3表示提示中的一个token。
        假设编号4='你好'，5='！'，2=EOS；编号与文字对应关系仅作示意。
    调用：
        result=model.generate(
            inputs=torch.tensor([[1,3]],dtype=torch.long,device=device),
            attention_mask=torch.tensor([[1,1]],device=device),
            max_new_tokens=5,temperature=1.0,top_k=0,top_p=1.0,
            do_sample=False,repetition_penalty=1.0,
            eos_token_id=2,use_cache=True,num_return_sequences=1
        )
    为逐行跟踪本函数，假设实际forward在三轮最后位置依次返回以下6个分数：
        第1轮：[0,1,0,1,5,2]，最大项编号4；
        第2轮：[0,1,0,1,2,5]，最大项编号5；
        第3轮：[0,1,6,1,2,3]，最大项编号2。
    它们是本例为generate提供的明确上游结果，不保证任意随机初始化模型都会这样输出。
    主干怎样计算logits见前面forward例子；下面完整追踪循环如何处理这些结果。

    1. 准备循环变量
        kwargs中没有input_ids，因此pop('input_ids',inputs)使用inputs。
        repeat(1,1)不增加行数：
            input_ids=[[1,3]]，形状[1,2]
            attention_mask=[[1,1]]，形状[1,2]
        没有传past_key_values，故缓存为None。
        finished=torch.zeros(1,dtype=bool) -> [False]。
        若给了streamer，此时先调用streamer.put([[1,3]]的CPU张量)。

    2. 第1轮：计算尚未缓存的全部提示
        past_len=0
        input_ids[:,0:]=[[1,3]]
        outputs=self.forward([[1,3]],mask=[[1,1]],past=None,use_cache=True)
        outputs.logits.shape=[1,2,6]
        每层返回K/V形状[1,2,1,2]，缓存长度2。

    3. 第1轮：为下一轮准备mask，再选择编号
        attention_mask.new_ones(1,1) -> [[1]]
        cat后attention_mask=[[1,1,1]]，长度3。
        logits=outputs.logits[:,-1,:]/1.0 -> [[0,1,0,1,5,2]]
        repetition_penalty=1，跳过重复惩罚。
        top_k=0，跳过top-k；top_p=1，跳过top-p。
        do_sample=False：
            argmax(logits,dim=-1,keepdim=True) -> next_token=[[4]]
        finished=[False]，torch.where保留4，不替换为EOS。

    4. 第1轮：追加、保存缓存、判断结束
        input_ids=cat([[1,3]],[[4]]) -> [[1,3,4]]
        past_key_values=outputs.past_key_values，缓存长度仍为2。
        若有streamer，发送[[4]]。
        next_token.squeeze(-1)=[4]；eq(2)=[False]。
        finished |= [False] -> [False]；不是全部结束，进入下一轮。
        注意：编号4刚选出来，还没有被送进forward，因此此时不在缓存中。

    5. 第2轮：只输入新增的4
        past_len=2
        input_ids[:,2:]=[[4]]
        forward收到[[4]]、完整mask=[[1,1,1]]和前2个位置的缓存。
        outputs.logits.shape=[1,1,6]，最后分数为[[0,1,0,1,2,5]]。
        新K/V形状[1,3,1,2]，缓存长度增至3。
        mask补1后为[[1,1,1,1]]。
        argmax得到next_token=[[5]]，finished仍为False，因此保留5。
        追加后input_ids=[[1,3,4,5]]，缓存长度3。
        streamer收到[[5]]；5!=2，finished仍为[False]。

    6. 第3轮：只输入新增的5
        past_len=3
        input_ids[:,3:]=[[5]]
        forward收到[[5]]和前3个位置的缓存。
        最后分数为[[0,1,6,1,2,3]]，新缓存长度4。
        mask补1后为[[1,1,1,1,1]]。
        argmax得到next_token=[[2]]；进入torch.where时finished仍为False，保留本轮的2。
        追加后input_ids=[[1,3,4,5,2]]，保存长度4的缓存。
        streamer收到[[2]]。
        eq(2)=[True]，finished从[False]更新为[True]。
        finished.all()为True，执行break，不再跑剩余两轮。

    7. 循环结束并返回
        若有streamer，调用streamer.end()收尾。
        默认result=tensor([[1,3,4,5,2]])，形状[1,5]。
        原提示长2，result[:,2:]才是新增编号[[4,5,2]]。
        调用方解码并跳过特殊标记后，可得到本例示意文字“你好！”。
        max_new_tokens=5是最多新增5个，不是总长最多5；本次遇到EOS，只新增3个。
        若额外传return_kv=True，返回：
            {'generated_ids':[[1,3,4,5,2]],'past_kv':两层各长4的缓存}
        最后选出的EOS还没有经过forward，所以缓存比完整序列少1个位置。

    【完整过滤例子：top-k、top-p、scatter和随机抽样】
    另取一个V=4的采样步骤，温度1、重复惩罚1、top_k=3、top_p=0.8、do_sample=True。
    假设进入过滤前，编号0..3的分数为：
        logits=[log(0.10),log(0.60),log(0.25),log(0.05)]
              ≈[-2.302585,-0.510826,-1.386294,-2.995732]

    1. top_k=3
        第3大分数是log(0.10)，仅编号3低于阈值：
            logits=[log(0.10),log(0.60),log(0.25),-inf]
        边界同分时可能保留超过k项，因为判断是“小于阈值”。

    2. 按分数降序排列
        sorted_indices=[1,2,0,3]
        sorted_logits=[log(0.60),log(0.25),log(0.10),-inf]

    3. 对保留下来的分数softmax
        原剩余权重和为0.95，因此排序后概率约为：
            [0.631579,0.263158,0.105263,0]
        cumsum约为[0.631579,0.894737,1.0,1.0]。
        与0.8比较，mask=[False,True,True,True]。

    4. 掩码右移
        mask[...,1:]=旧mask[...,:-1].clone()
        mask[...,0]=False
        结果=[False,False,True,True]。
        保留首次让累计概率超过0.8的编号2，而不是把它也删除。

    5. scatter放回原词表编号
        排序位置0对应编号1，保留；
        排序位置1对应编号2，保留；
        排序位置2对应编号0，删除；
        排序位置3对应编号3，删除。
        原编号顺序的删除掩码=[True,False,False,True]。
        logits变为[-inf,log(0.60),log(0.25),-inf]。

    6. 再softmax并抽样
        最终编号0..3的概率=[0,0.60/0.85,0.25/0.85,0]
                            ≈[0,0.705882,0.294118,0]
        multinomial(...,num_samples=1)返回形状[B,1]，可能抽到编号1或2。
        假设本次抽到2，则next_token=[[2]]；随机抽样不保证每次都相同。
        do_sample=False则直接argmax，本组分数会选编号1。

    【温度与重复惩罚也展开算一次】
        logits=[6,-2,4,1]，temperature=2 -> [3,-1,2,0.5]
        某行input_ids=[0,1,0]，unique后seen=[0,1]。
        repetition_penalty=1.2：
            已见编号0正分数3 -> 3/1.2=2.5；
            已见编号1负分数-1 -> -1*1.2=-1.2。
        处理后logits=[2.5,-1.2,2,0.5]，再接top-k/top-p。
        编号0虽然出现两次，本轮也只调整一次；提示词中的编号同样算已见。
        temperature和repetition_penalty应为正数，正top_k不能大于词表大小。

    【批量结束、复制和无缓存分支】
        若输入批次为[A,B]，num_return_sequences=2：
            repeat(2,1)的行顺序是[A,B,A,B]，mask以相同顺序复制。
            外部传入的past_key_values不会在这里自动复制，batch维必须由调用方保证匹配。
        假设两行当前finished=[True,False]，采样得到[[4],[5]]：
            finished.unsqueeze(-1)=[[True],[False]]
            填满EOS的张量=[[2],[2]]
            where后next_token=[[2],[5]]
            更新finished仍为[True,False]，继续循环。
        当下一轮第二行也生成2，finished才变为[True,True]并停止；
        所以先结束的行可能追加多个EOS，本函数没有改用PAD填充。
        eos_token_id=None时不按EOS提前退出，运行到新增数上限。
        use_cache=False时每轮past_key_values=None、past_len=0；
            上面三轮分别把[[1,3]]、[[1,3,4]]、[[1,3,4,5]]完整送进forward。
        inputs与input_ids都可传入；kwargs中的input_ids优先。
        给已有缓存继续生成时，input_ids应包含对应的缓存前缀及尚未缓存的新token。

    数据流：完整提示 -> 取未缓存后缀 -> forward -> 最后位置logits -> 温度/惩罚/过滤
            -> 抽样或argmax -> 追加一个编号 -> 更新缓存与finished -> 重复 -> 完整结果。

    装饰器inference_mode关闭本次生成的梯度记录，但不替代model.eval()；训练态Dropout仍由self.training决定。
    '''
    @torch.inference_mode()
    def generate(self, inputs=None, attention_mask=None, max_new_tokens=8192, temperature=0.85, top_p=0.85, top_k=50, eos_token_id=2, streamer=None, use_cache=True, num_return_sequences=1, do_sample=True, repetition_penalty=1.0, **kwargs):
        # pop 优先取并移除 kwargs 中的 input_ids，否则用 inputs；repeat 沿 batch 轴整体复制，序列轴复制 1 次。
        input_ids = kwargs.pop("input_ids", inputs).repeat(num_return_sequences, 1)
        # 有 mask 就以相同顺序复制，保持它与输入逐行对应；没有 mask 则保留 None。
        attention_mask = attention_mask.repeat(num_return_sequences, 1) if attention_mask is not None else None
        # 取出可选的外部历史缓存，同时从 kwargs 删除，避免后面传参时重复传入。
        past_key_values = kwargs.pop("past_key_values", None)
        # 为复制后的每条序列建立布尔结束标记，全为 False；设备与输入一致。
        finished = torch.zeros(input_ids.shape[0], dtype=torch.bool, device=input_ids.device)
        # 若有 streamer，先发送 CPU 上的整个提示批次；是否跳过提示显示由 streamer 配置决定。
        if streamer: streamer.put(input_ids.cpu())
        # 最多循环 max_new_tokens 轮，每轮为批次中的每行追加一个 token；_ 表示循环编号不需要使用。
        for _ in range(max_new_tokens):
            # 从第 0 层 Key 的 [B,历史长度,Nkv,D] 读出已缓存长度；无缓存则为 0。
            past_len = past_key_values[0][0].shape[1] if past_key_values else 0
            # 只将未缓存后缀送入 forward，但 mask 覆盖全部上下文；**kwargs 可继续传 logits_to_keep 等参数。
            outputs = self.forward(input_ids[:, past_len:], attention_mask, past_key_values, use_cache=use_cache, **kwargs)
            # 为即将追加的新 token 补一列有效标记 1；new_ones 保持 mask 的 dtype/device，供下一轮使用。
            attention_mask = torch.cat([attention_mask, attention_mask.new_ones(attention_mask.shape[0], 1)], -1) if attention_mask is not None else None
            # 只取本次最后位置的 [B,V] 词表分数，因为它预测接下来一个 token，再除以温度调整采样分布。
            logits = outputs.logits[:, -1, :] / temperature
            # 系数为 1 不做重复调整；通常用大于 1 的正数惩罚重复，小于 1 的正数反而鼓励重复。
            if repetition_penalty != 1.0:
                # 不同样本出现过的编号不同，因此逐行处理它们各自的重复候选。
                for i in range(input_ids.shape[0]):
                    # 一行有三个语句：去重得到 seen；取出这些编号的分数；正数除系数、非正数乘系数后写回。
                    '''
                    1. torch.unique 的例子：
                       假设 input_ids[i] = tensor([3, 1, 3, 4, 1])，表示第 i 条序列已出现的 token 编号。
                       torch.unique(input_ids[i]) 去掉重复编号，默认按编号排序，得到 seen = tensor([1, 3, 4])。
                       同一个 token 即使出现多次，在本轮也只调整一次；这里不按出现次数加重惩罚。

                    2. score 和 logits 的例子：
                       logits 的形状为 [批次大小, 词表大小]，logits[i] 是第 i 条序列的下一 token 分数。
                       假设词表有 5 个 token，每一列对应一个 token 编号（从 0 开始）：
                       token 编号：        0     1     2      3     4
                       调整前 logits[i]：[0.5,  2.0,  1.0,  -2.0,  0.0]
                       seen = [1, 3, 4] 用作列索引，因此 score = logits[i, seen] = tensor([2.0, -2.0, 0.0])。
                       score 只取出已出现的 token 的分数，依次对应编号 1、3、4。

                       若 repetition_penalty = 2.0，下面逐列看原值 -> 新值：
                       第 0 列（token 0，未出现）： 0.5 ->  0.5，不参与重复惩罚，保持原值。
                       第 1 列（token 1，已出现）： 2.0 ->  1.0，正数除以 2，分数变小。
                       第 2 列（token 2，未出现）： 1.0 ->  1.0，不参与重复惩罚，保持原值。
                       第 3 列（token 3，已出现）：-2.0 -> -4.0，负数乘以 2，分数变小（变得更负）。
                       第 4 列（token 4，已出现）： 0.0 ->  0.0，走乘法分支，零乘以 2 仍然是零。

                       因此，torch.where 得到的结果是 [1.0, -4.0, 0.0]，再写回 logits 的第 1、3、4 列：
                       token 编号：        0     1     2      3     4
                       调整前 logits[i]：[0.5,  2.0,  1.0,  -2.0,  0.0]
                       调整后 logits[i]：[0.5,  1.0,  1.0,  -4.0,  0.0]
                       可以看到，重复候选 token 1 的分数从 2.0 降到 1.0，token 3 从 -2.0 降到 -4.0。
                       注意：-4.0 < -2.0，虽然绝对值从 2 变成 4，但分数本身变小，因此也是惩罚。
                       未出现的 token 0、2 的分数不变；重复候选 token 4 因为分数为零，也保持不变。

                    3. 为什么这样能惩罚重复（假设 repetition_penalty > 1）：
                       logits 是未经 softmax 的分数，可以为正或负；分数越大，候选 token 越有优势。
                       正数除以大于 1 的系数会变小，负数乘以该系数会更负，两者都降低了重复候选的分数。
                       若负数也用除法，例如 -2.0 / 2.0 = -1.0，分数反而变大，会鼓励重复。
                       softmax 中 p_j / p_k = exp(logit_j - logit_k)，所以降低重复候选的分数，
                       会降低它相对未出现候选的概率比；零分数保持不变，不会受到直接惩罚。
                       注意：归一化会同时受其他候选影响，因此不保证每个重复 token 的绝对概率都下降。
                    '''
                    seen = torch.unique(input_ids[i]); score = logits[i, seen]; logits[i, seen] = torch.where(score > 0, score / repetition_penalty, score * repetition_penalty)
            # top_k 为正才开启数量过滤；0 或负值跳过这个分支。
            if top_k > 0:
                # topk(...)[0] 取前 k 大的值，[...,-1,None] 取第 k 大并保留 [B,1] 方便广播；更小的全设 -inf。
                logits[logits < torch.topk(logits, top_k)[0][..., -1, None]] = -float('inf')
            # top_p 小于 1 才开启累计概率过滤；常用有效范围为 0<top_p<=1。
            if top_p < 1.0:
                # 按每行词表分数降序排列，得到排序值与它们原来的 token 编号，两者均为 [B,V]。
                sorted_logits, sorted_indices = torch.sort(logits, descending=True)
                # 先得到排序后的概率，再沿词表轴累计；超过 p 的位置先标 True，作为待删除掩码。
                mask = torch.cumsum(torch.softmax(sorted_logits, dim=-1), dim=-1) > top_p
                # 将删除标记右移，保留首次越界候选并强制保留第一项；clone 避免重叠切片读写冲突。
                mask[..., 1:], mask[..., 0] = mask[..., :-1].clone(), 0
                # scatter 把排序位置的布尔标记写回原 token 编号的位置，再把应删除的候选分数设为 -inf。
                logits[mask.scatter(1, sorted_indices, mask)] = -float('inf')
            # 采样分支用 softmax+multinomial 按给定的随机概率抽一个编号；贪心分支取 argmax；两者均返回 [B,1]。
            next_token = torch.multinomial(torch.softmax(logits, dim=-1), num_samples=1) if do_sample else torch.argmax(logits, dim=-1, keepdim=True) # 一般走argmax
            # finished:[B] 插轴为 [B,1]；已结束行选填满 EOS 的张量，未结束行保留本轮新选的 token。
            if eos_token_id is not None: next_token = torch.where(finished.unsqueeze(-1), next_token.new_full((next_token.shape[0], 1), eos_token_id), next_token)
            # 沿序列轴追加新编号，例如 [B,3] 和 [B,1] 拼成 [B,4]；每行长度统一增加 1。
            input_ids = torch.cat([input_ids, next_token], dim=-1)
            # 开启缓存则保存本轮 forward 的结果；关闭时明确设 None，下轮 past_len=0、重算完整输入。
            past_key_values = outputs.past_key_values if use_cache else None
            # 把本轮的 [B,1] 新编号移到 CPU 给 streamer，便于它逐步解码显示。
            if streamer: streamer.put(next_token.cpu())
            # 只有给出 EOS 编号时才维护结束状态并执行提前停止。
            if eos_token_id is not None:
                # squeeze 去掉末尾单元素轴，eq 逐行检查是否等于 EOS；|= 保留“之前已经结束”的 True 状态。
                finished |= next_token.squeeze(-1).eq(eos_token_id)
                # 所有行都已结束就跳出整个生成循环；仅部分结束时继续为其它行生成。
                if finished.all(): break
        # 循环结束后通知 streamer 收尾，例如输出它尚未显示的解码缓冲。
        if streamer: streamer.end()
        # 调用方要求缓存时返回字典；最后刚选出的 token 未经过 forward，因此通常尚不在 past_kv 中。
        if kwargs.get("return_kv"): return {'generated_ids': input_ids, 'past_kv': past_key_values}
        # 默认返回包含原提示的完整整数张量，由调用方裁掉提示并交给 tokenizer 解码。
        return input_ids
