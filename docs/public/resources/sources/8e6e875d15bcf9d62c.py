# LoRA 适配器：为选中的线性层叠加 B(A(x))，支持单独保存、加载与合并低秩权重。
# 本实现没有额外的 alpha/rank 缩放；是否冻结基座参数由训练脚本决定。
import torch
from torch import optim, nn


# 定义Lora网络结构
# 用 rank 维瓶颈近似权重增量；A: [rank,in]，B: [out,rank]。
class LoRA(nn.Module):
    # 构造无偏置的 A/B 线性层；rank 是瓶颈宽度，决定新增参数量 rank*(in+out)。
    def __init__(self, in_features, out_features, rank):
        super().__init__()
        self.rank = rank  # LoRA的秩（rank），控制低秩矩阵的大小
        self.A = nn.Linear(in_features, rank, bias=False)  # 低秩矩阵A
        self.B = nn.Linear(rank, out_features, bias=False)  # 低秩矩阵B
        # 矩阵A高斯初始化
        # A 随机初始化、B 零初始化，因此初始 LoRA 增量为 0；这里 .data 绕过梯度记录，仅用于初始化。
        self.A.weight.data.normal_(mean=0.0, std=0.02)
        # 矩阵B全0初始化
        self.B.weight.data.zero_()

    # 输入 [...,in] 经 A 降到 rank，再经 B 回到 out；返回 [...,out] 的残差增量。
    def forward(self, x):
        return self.B(self.A(x))


# 遍历输入输出维度相等的 Linear 并挂载 LoRA 分支；此处并非给所有 Linear 加适配器。
def apply_lora(model, rank=16):
    for name, module in model.named_modules():
        if isinstance(module, nn.Linear) and module.in_features == module.out_features:
            lora = LoRA(module.in_features, module.out_features, rank=rank).to(model.device)
            # 给 nn.Module 挂载子模块会注册其参数；改写 forward 后自动叠加适配器结果。
            setattr(module, "lora", lora)
            original_forward = module.forward

            # 显式绑定
            # 默认参数捕获当前层对象，避免循环闭包引用最后一层；输出为原层结果加 LoRA 增量。
            def forward_with_lora(x, layer1=original_forward, layer2=lora):
                return layer1(x) + layer2(x)

            module.forward = forward_with_lora


# 清理 DDP 的 module. 前缀后，将适配器参数按完整模块路径分配到对应层。
def load_lora(model, path):
    """把保存到文件里的 LoRA 参数，恢复到当前 module.lora 这个 LoRA 模块中。"""
    # PyTorch：load 读取序列化对象；map_location 指定张量加载设备，CPU 加载可避免先占用 GPU 显存。
    state_dict = torch.load(path, map_location=model.device)#从 path 读取权重文件。
    state_dict = {(k[7:] if k.startswith('module.') else k): v for k, v in state_dict.items()}
    #多卡训练时，权重名字可能是：module.layers.0.attention.q_proj.lora.lora_a.weight,所以若键名以 module. 开头，就去掉前 7 个字符。
    for name, module in model.named_modules():#接着遍历模型全部子模块
        if hasattr(module, 'lora'):#若它已经挂载 LoRA：
            lora_state = {k.replace(f'{name}.lora.', ''): v for k, v in state_dict.items() if f'{name}.lora.' in k}#就从总权重字典中挑出只属于该 LoRA 层的参数：
            # PyTorch：load_state_dict 按参数/缓冲区名字恢复状态；strict=False 允许缺失/额外键，但不忽略同名张量形状不匹配。
            module.lora.load_state_dict(lora_state)#module.lora.load_state_dict(...) 是 PyTorch nn.Module 自带的“加载权重”函数。把这一层 LoRA 的 A、B 矩阵权重加载进去。
            # lora_state={
            #     "lora_a.weight": tensor(...),
            #     "lora_b.weight": tensor(...)
            # }


# 仅导出适配器权重到 CPU FP16 文件；基座权重需要另外保留。
def save_lora(model, path):
    raw_model = getattr(model, '_orig_mod', model)
    state_dict = {}
    for name, module in raw_model.named_modules():
        if hasattr(module, 'lora'):
            clean_name = name[7:] if name.startswith("module.") else name
            lora_state = {f'{clean_name}.lora.{k}': v.cpu().half() for k, v in module.lora.state_dict().items()}
            state_dict.update(lora_state)
    # PyTorch：save 将对象序列化；这里保存 state_dict 等状态，恢复时仍需用匹配的模型配置构建网络。
    torch.save(state_dict, path)


# 将增量 B.weight @ A.weight 加入基座权重，导出不依赖 LoRA 分支的 state_dict。
def merge_lora(model, lora_path, save_path):
    load_lora(model, lora_path)#先把 LoRA 文件中的 A.weight、B.weight 加载到模型各层的 module.lora 中。
    raw_model = getattr(model, '_orig_mod', model)
    state_dict = {k: v.cpu().half() for k, v in raw_model.state_dict().items() if '.lora.' not in k}#先复制原模型全部权重到待保存字典中，但排除 LoRA 权重。
    for name, module in raw_model.named_modules():#遍历所有模块。
        if isinstance(module, nn.Linear) and '.lora.' not in name:#只处理正常的线性层，并跳过 LoRA 自己内部的两个线性层 lora.A 与 lora.B。
            # clone 创建独立副本，随后进行合并不会通过共享存储修改原始基座参数。
            state_dict[f'{name}.weight'] = module.weight.data.clone().cpu().half()
            if hasattr(module, 'lora'):#如果这个线性层有 LoRA，就计算：B @ A W_merged = W + B @ A，B @ A 是矩阵乘法
                state_dict[f'{name}.weight'] += (module.lora.B.weight.data @ module.lora.A.weight.data).cpu().half()
    torch.save(state_dict, save_path)
