# RoPE 相关张量操作练习；下方可执行示例演示 unsqueeze 如何增加长度为 1 的维度。
import torch

# x=torch.tensor([[1,2,3,4,5]])
# y=torch.tensor([[6,7,8,9,10]])

# condition=x>3
# res=torch.where(condition,x,y)#像三目运算符 满足condition的取x 不满足的取y
# print(res)

# 生成等差序列
# t=torch.arange(0,10,2)
# print(t)

# t2=torch.arange(5,0,-1)
# print(t2)

# 外积
# v1=torch.tensor([1,2,3])
# v2=torch.tensor([4,5,6])
# res=torch.outer(v1,v2)#外积,1*4,1*5,1*6;2*4,2*5,2*6;3*4,3*5,3*6
# print(res)

# 拼接
# t1=torch.tensor([[[1,2,3],[4,5,6]],[[7,8,9],[10,11,12]]])
# t2=torch.tensor([[[7,8,9],[10,11,12]],[[13,14,15],[16,17,18]]])
# print(torch.cat((t1,t2),dim=0))#按行拼接
# print(torch.cat((t1,t2),dim=1))#按列拼接
# print(torch.cat((t1,t2),dim=-1))#按最后一个维度拼接

# 增加一个维度
# 这里是 [2,3] 的二维矩阵；dim=0 增轴后变为 [1,2,3]，元素个数不变。
t1=torch.tensor([[1,2,3],[4,5,6]])
# unsqueeze(input,dim) 返回共享数据的视图；dim=1 会变为 [2,1,3]，dim=-1 会变为 [2,3,1]。
t2=torch.unsqueeze(t1,dim=0)#在第0维增加一个维度
print(t1.shape)
print(t2)
print(t2.shape)