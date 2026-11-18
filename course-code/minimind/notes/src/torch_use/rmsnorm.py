# RMSNorm 基础运算练习：rsqrt 计算平方根的倒数，ones 创建全 1 张量。
import torch

# PyTorch：rsqrt(x)=1/sqrt(x)，按元素计算；此示例使用正浮点标量。
# 输入为浮点标量 4.0，rsqrt 的输出为 0.5；标量张量的 shape 是 []。
t=torch.rsqrt(torch.tensor(4.0))
print(t)

# ones(3,4) 创建形状 [3,4] 的全 1 张量；未指定 device/dtype 时使用默认设备与浮点类型。
t2=torch.ones(3,4)
print(t2)