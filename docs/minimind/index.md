---
title: MiniMind
project: minimind
projectOverview: true
---

# MiniMind

从梯度与预训练出发，按训练机制、Transformer 架构、模型源码、PPO、MoE 与 LoRA 阅读。相关原理、代码和数值例子放在同一主题下，提供完整讲义下载与源码对照。

[开始阅读 →](/minimind/b00-01) · [返回课程首页](/) · [查看学习路线](/guide/)

## 你会学到什么

预训练与 SFT · Transformer · PPO / RLHF · MoE / LoRA

## 基础与预训练

- [01 · 梯度、反向传播与梯度下降](/minimind/b00-01)
- [02 · Tokenizer 训练与原理](/minimind/s0747f098-01)
- [03 · 预训练完整流程](/minimind/b01-01)
- [04 · Next Token：预测目标与损失计算](/minimind/b04-01)
- [05 · Next Token：并行训练与前缀共享](/minimind/b04-02)
- [06 · Next Token：反向传播与上下文学习](/minimind/b04-03)
- [07 · 预训练源码：数据、模型与前向计算](/minimind/s1545a2c4-01)
- [08 · 预训练源码：训练循环、评估与工程细节](/minimind/s1545a2c4-02)
- [09 · 困惑度与模型评估](/minimind/s1515c2c3-01)

## 训练机制与 SFT

- [10 · 混合精度：FP16、AMP 与梯度裁剪](/minimind/b02-01)
- [11 · Loss Scaling：梯度传播与数值保护](/minimind/b02-02)
- [12 · 梯度累积与 Loss 平均](/minimind/b03-01)
- [13 · SFT 与三种 Mask](/minimind/b05-01)

## Transformer 架构

- [14 · Encoder 与 Decoder-only](/minimind/se862b370-01)
- [15 · Attention：QKV、打分与加权求和](/minimind/b06-01)
- [16 · Attention：多头结构与 QKV 的分工](/minimind/b06-02)
- [17 · Attention：反向传播与共享参数](/minimind/b06-03)
- [18 · MHA：多头投影、维度与参数量](/minimind/b07-01)
- [19 · MHA：值向量汇合与多头梯度](/minimind/b07-02)
- [20 · KV Cache：缓存原理与增量计算](/minimind/b08-01)
- [21 · KV Cache：Prefill、Decode 与训练阶段](/minimind/b08-02)
- [22 · GQA：分组结构与缓存开销](/minimind/b08-03)
- [23 · GQA：共享梯度与 MHA、MQA 对比](/minimind/b08-04)
- [24 · 位置编码：Attention 的顺序信息](/minimind/b09-01)
- [25 · RoPE：旋转表示与相对位置](/minimind/b09-02)
- [26 · YaRN：长上下文外推与频率缩放](/minimind/b09-03)
- [27 · RoPE 与 YaRN：频率分工与综合例子](/minimind/b09-04)
- [28 · 位置编码：绝对位置与正弦编码](/minimind/b09-05)
- [29 · 归一化：LayerNorm、RMSNorm 与 Pre-Norm](/minimind/b10-01)
- [30 · RMSNorm：数值尺度、梯度裁剪与权重](/minimind/b10-02)
- [31 · SiLU 与门控 FFN](/minimind/b11-01)
- [32 · MiniMind 整体架构](/minimind/b13-01)
- [33 · Dense Model 重点复习](/minimind/b12-01)

## 模型源码与推理

- [34 · 理论之外的 Tensor 操作](/minimind/b14-01)
- [35 · 模型源码：配置、基础组件与 RoPE](/minimind/b15-01)
- [36 · 模型源码：Attention 的构造与前向计算](/minimind/b15-02)
- [37 · 模型源码：FFN、MoE 与 Decoder Block](/minimind/b15-03)
- [38 · 模型源码：Transformer 主干、LM Head 与 Loss](/minimind/b15-04)
- [39 · 模型源码：自回归生成与实现要点](/minimind/b15-05)
- [40 · 推理：generate 流程与采样策略](/minimind/b16-01)
- [41 · 推理：KV Cache 调用链与流式输出](/minimind/b16-02)

## 强化学习与 PPO 原理

- [42 · 强化学习基础](/minimind/s6350dbe1-01)
- [43 · 策略梯度与 Actor-Critic](/minimind/s3503af2f-01)
- [44 · PPO 算法详解](/minimind/se8dc6aaa-01)
- [45 · 强化学习：轨迹、价值与策略梯度](/minimind/b17-01)
- [46 · 策略梯度：Advantage、Critic 与 GAE](/minimind/b17-02)
- [47 · PPO：重要性采样、裁剪目标与旧策略](/minimind/b17-03)
- [48 · RLHF：模型分工、奖励与参数更新](/minimind/b17-04)
- [49 · RLHF 与 PPO 的 18 个关键问题](/minimind/sed92650a-01)
- [50 · PPO 梯度更新与反向传播](/minimind/sc84b38de-01)
- [51 · PPO 裁剪目标与通用实现](/minimind/s41b0a574-01)

## PPO 采样与训练

- [52 · PPO 重点复习](/minimind/b19-01)
- [53 · Reward Model：数据与 PyTorch 接口](/minimind/b18-01)
- [54 · Reward Model：偏好损失、梯度与评分尺度](/minimind/b18-02)
- [55 · Rollout 从零到完整流程](/minimind/b20-01)
- [56 · Rollout 的 PyTorch 与 SGLang 实现](/minimind/sbe84682d-01)
- [57 · PPO 代码：模型角色与 PyTorch 基础](/minimind/b21-01)
- [58 · PPO 代码：DDP 同步、KL 监控与近似](/minimind/b21-02)
- [59 · PPO 代码：采样、GAE 与 Actor-Critic 更新](/minimind/b21-03)
- [60 · PPO 中的两类 KL 散度](/minimind/s0c014541-01)
- [61 · PPO 代码中的 GAE](/minimind/scb9fb90e-01)
- [62 · PPO 训练完整数值例子](/minimind/b22-01)

## MoE

- [63 · MoE：专家路由与 Token 分发](/minimind/b23-01)
- [64 · MoE：负载均衡与稀疏计算](/minimind/b23-02)
- [65 · MoE 源码：前向计算与梯度路径](/minimind/b23-03)
- [66 · MoE 源码：辅助损失与训练实现](/minimind/b23-04)

## LoRA

- [67 · LoRA：低秩更新与完整工作流程](/minimind/b24-01)
- [68 · LoRA 数学：行列式、特征值与坐标变换](/minimind/b24-02)
- [69 · LoRA 数学：SVD 与低秩因子构造](/minimind/b24-03)
- [70 · LoRA 前向、梯度与部署](/minimind/s4859f99c-01)
- [71 · LoRA 训练代码](/minimind/b25-01)

