import argparse
import os
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
import datasets
import torch
from torch import nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset
from transformers import AutoTokenizer
from model.model_minimind import MiniMindConfig, MiniMindModel

def encode_messages(tokenizer, messages):
    text = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=False
    )
    return tokenizer(text, add_special_tokens=False)["input_ids"]


class RewardDataset(Dataset):
    def __init__(self, path, tokenizer, max_length=1024, max_samples=None):
        samples = datasets.load_dataset("json", data_files=str(path), split="train")
        if max_samples is not None:
            samples = samples.select(range(min(max_samples, len(samples))))
        def encode_pair(sample, index):
            chosen, rejected = sample["chosen"], sample["rejected"]
            for messages in (chosen, rejected):
                if not isinstance(messages, list) or len(messages) < 2:
                    raise ValueError(f"样本 {index}: chosen/rejected 必须是含上下文和回答的消息列表")
                if any(not isinstance(m, dict) or not isinstance(m.get("content"), str)
                       or not isinstance(m.get("role"), str) for m in messages):
                    raise ValueError(f"样本 {index}: 每条消息必须包含字符串 role 和 content")
                if messages[-1]["role"] != "assistant":
                    raise ValueError(f"样本 {index}: 最后一条消息必须是 assistant 回答")
            if chosen[:-1] != rejected[:-1]:
                raise ValueError(f"样本 {index}: 两个回答必须对应相同的对话上下文")
            c = encode_messages(tokenizer, chosen)
            r = encode_messages(tokenizer, rejected)
            keep = (0 < len(c) <= max_length and 0 < len(r) <= max_length
                    and bool(chosen[-1]["content"].strip())
                    and bool(rejected[-1]["content"].strip()) and c != r)
            return {"chosen_ids": c, "rejected_ids": r, "keep": keep}
        total = len(samples)
        samples = samples.map(encode_pair, with_indices=True,
                              remove_columns=samples.column_names)
        self.samples = samples.filter(lambda sample: sample["keep"])
        print(f"偏好对: 保留 {len(self.samples)}/{total}，过滤 {total - len(self.samples)} 条")
        if not len(self.samples):
            raise ValueError("没有可训练样本，请检查数据或增大 --max_seq_len")
        self.pad_id = tokenizer.pad_token_id
        if self.pad_id is None:
            self.pad_id = tokenizer.eos_token_id
        if self.pad_id is None:
            raise ValueError("tokenizer 必须提供 pad_token_id 或 eos_token_id")
        
    def __len__(self):
        return len(self.samples)
    
    def __getitem__(self, index):
        return self.samples[index]
    
    def collate(self, batch):
        sequences = [row[key] for key in ("chosen_ids", "rejected_ids") for row in batch]
        width = max(map(len, sequences))
        ids = torch.full((len(sequences), width), self.pad_id, dtype=torch.long)
        mask = torch.zeros_like(ids)
        for i, sequence in enumerate(sequences):
            ids[i, :len(sequence)] = torch.tensor(sequence)
            mask[i, :len(sequence)] = 1
        return ids, mask

    
class MiniMindRewardModel(nn.Module):

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.model = MiniMindModel(config)
        self.reward_head = nn.Linear(config.hidden_size, 1, bias=False)
        nn.init.normal_(self.reward_head.weight, mean=0.0, std=0.02)

    def forward(self, input_ids, attention_mask):
        hidden, _, aux_loss = self.model(input_ids, attention_mask=attention_mask)
        last = attention_mask.sum(dim=1) - 1
        final_hidden = hidden[torch.arange(hidden.size(0), device=hidden.device), last]
        scores = self.reward_head(final_hidden).squeeze(-1)
        return scores, aux_loss
    
    @torch.no_grad()
    def get_score(self, tokenizer, messages):
        ids = encode_messages(tokenizer, messages)
        if not ids or len(ids) > self.config.max_position_embeddings:
            raise ValueError("输入为空或超过模型位置长度限制")
        device = next(self.parameters()).device
        input_ids = torch.tensor([ids], dtype=torch.long, device=device)
        was_training = self.training
        self.eval()
        try:
            scores, _ = self(input_ids, torch.ones_like(input_ids))
            return scores.item()
        finally:
            self.train(was_training)


def load_reward_model(path, device="cpu"):
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    config = MiniMindConfig(**checkpoint["config"])
    model = MiniMindRewardModel(config)
    model.load_state_dict(checkpoint["model"], strict=True)
    return model.to(device).eval()


def save_reward_model(model, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    torch.save({"config": model.config.to_dict(),
                "model": {k: v.detach().cpu() for k, v in model.state_dict().items()}}, temporary)
    temporary.replace(path)

    
def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data_path", default=str(ROOT / "dataset/dpo.jsonl"))
    parser.add_argument("--tokenizer_path", default=str(ROOT / "model"))
    parser.add_argument("--from_weight", default="full_sft", help="SFT 权重前缀；none 表示随机初始化")
    parser.add_argument("--init_checkpoint", help="显式指定 SFT state_dict 的 .pth 路径")
    parser.add_argument("--save_path", help="默认保存为项目 out/reward_<hidden_size>[_moe].pth")
    parser.add_argument("--hidden_size", type=int, default=768)
    parser.add_argument("--num_hidden_layers", type=int, default=8)
    parser.add_argument("--use_moe", action="store_true")
    parser.add_argument("--max_seq_len", type=int, default=1024)
    parser.add_argument("--batch_size", type=int, default=2, help="每批偏好对数量，实际前向序列数为两倍")
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--learning_rate", type=float, default=1e-5)
    parser.add_argument("--max_steps", type=int, help="最多更新次数，用于快速验证流程")
    parser.add_argument("--max_samples", type=int, help="只读取前 N 条数据用于教学实验")
    parser.add_argument("--log_interval", type=int, default=10)
    parser.add_argument("--device", default="cuda:0" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--score_checkpoint", help="指定训练好的 RM 文件，进入评分模式")
    parser.add_argument("--prompt", default="1+1等于几？")
    parser.add_argument("--response", default="等于2。")
    args = parser.parse_args()

    for name in ("hidden_size", "num_hidden_layers", "max_seq_len", "batch_size", "epochs",
                 "learning_rate", "log_interval", "max_steps", "max_samples"):
        value = getattr(args, name)
        if value is not None and value <= 0:
            parser.error(f"--{name} 必须大于 0")

    torch.manual_seed(42)
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer_path)

    if args.score_checkpoint:
        model = load_reward_model(args.score_checkpoint, args.device)
        messages = [{"role": "user", "content": args.prompt},
                    {"role": "assistant", "content": args.response}]
        print(f"reward = {model.get_score(tokenizer, messages):.6f}")
        return
    
    if args.hidden_size % 16:
        parser.error("--hidden_size 必须是 16 的倍数")

    config = MiniMindConfig(hidden_size=args.hidden_size, num_hidden_layers=args.num_hidden_layers,use_moe=args.use_moe)

    if args.max_seq_len > config.max_position_embeddings:
        parser.error("--max_seq_len 超过模型位置长度限制")

    model = MiniMindRewardModel(config)
    suffix = "_moe" if args.use_moe else ""

    if args.init_checkpoint or args.from_weight != "none":
        path = args.init_checkpoint or ROOT / "out" / f"{args.from_weight}_{args.hidden_size}{suffix}.pth"
        if not Path(path).is_file():
            parser.error(f"找不到 SFT 权重 {path}；请提供 --init_checkpoint，或用 --from_weight none 演示")
        weights = torch.load(path, map_location="cpu", weights_only=True)
        backbone = {k[len("model."):]: v for k, v in weights.items() if k.startswith("model.")}
        model.model.load_state_dict(backbone, strict=True)
        print(f"已加载 SFT 骨干: {path}；reward_head 随机初始化")
    else:
        print("演示模式：骨干和评分头均随机初始化")

    train_data = RewardDataset(args.data_path, tokenizer, args.max_seq_len, args.max_samples)
    loader = DataLoader(train_data, batch_size=args.batch_size, shuffle=True,
                        collate_fn=train_data.collate, num_workers=0)
    model.to(args.device).train()
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate)
    step = 0
    
    for epoch in range(args.epochs):
        for input_ids, mask in loader:
            input_ids, mask = input_ids.to(args.device), mask.to(args.device)
            scores, aux_loss = model(input_ids, mask)
            chosen, rejected = scores.chunk(2)
            ranking_loss = -F.logsigmoid(chosen.float() - rejected.float()).mean()
            loss = ranking_loss + aux_loss
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            step += 1
            if step == 1 or step % args.log_interval == 0:
                accuracy = (chosen > rejected).float().mean().item()
                print(f"epoch={epoch + 1} step={step} loss={loss.item():.4f} "
                      f"ranking_loss={ranking_loss.item():.4f} accuracy={accuracy:.3f} "
                      f"chosen={chosen.mean().item():.3f} rejected={rejected.mean().item():.3f}")
            if args.max_steps is not None and step >= args.max_steps:
                break
        path = args.save_path or ROOT / "out" / f"reward_{args.hidden_size}{suffix}.pth"
        save_reward_model(model, path)
        print(f"已保存奖励模型: {path}")
        if args.max_steps is not None and step >= args.max_steps:
            break
if __name__ == "__main__":
    main()
