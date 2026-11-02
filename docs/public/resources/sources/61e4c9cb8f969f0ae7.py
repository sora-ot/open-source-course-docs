# 学习辅助入口：先展示原始 JSONL，按需调用项目 Dataset 查看 token、标签和张量形状。
"""查看 JSONL 样本；--processed 额外查看项目 Dataset 返回的张量。"""

import argparse
import json
from pathlib import Path
import tempfile


ROOT = Path(__file__).resolve().parent


# 选择文件/演示样本，检查格式，并按 processed 开关决定是否加载训练依赖。
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path, help="实际 JSONL 数据文件路径")
    parser.add_argument("--count", type=int, default=3, help="显示几条样本，默认 3")
    parser.add_argument("--processed", action="store_true", help="查看 token 编号和 labels（需要训练依赖）")
    parser.add_argument("--max-length", type=int, default=64)
    args = parser.parse_args()
    if args.count < 1 or args.max_length < 2:
        parser.error("count 必须至少为 1，max-length 必须至少为 2")

    path = args.path
    if path is None:
        path = next(iter(sorted((ROOT / "dataset").glob("*.jsonl"))), None)

    samples = []
    if path is None:
        print("没有找到 dataset/*.jsonl，以下是手写演示数据，不是真实训练数据。")
        samples = [
            {"text": "春天来了，花园里的花开了。"},
            {"text": "北京是中国的首都。"},
            {"text": "学习 Python，可以从打印一行文字开始。"},
        ][:args.count]
    else:
        print(f"数据文件：{path.resolve()}")
        try:
            with path.open(encoding="utf-8") as source:
                for line_number, line in enumerate(source, 1):
                    if not line.strip():
                        continue
                    try:
                        samples.append(json.loads(line))
                    except json.JSONDecodeError as exc:
                        parser.error(f"第 {line_number} 行不是有效 JSON：{exc}")
                    if len(samples) >= args.count:
                        break
        except OSError as exc:
            parser.error(str(exc))

    if not samples:
        parser.error("文件中没有样本")
    for index, sample in enumerate(samples):
        print(f"\n===== 原始样本 {index} =====")
        print(json.dumps(sample, ensure_ascii=False, indent=2))

    print("\nJSONL 每行是一条样本。text 是预训练文本；conversations 是对话列表。")
    # 默认仅查看 JSON，不依赖 torch/transformers；只有 processed 模式才导入训练相关包。
    if not args.processed:
        print("加上 --processed 可查看 Dataset 处理后的 input_ids 和 labels。")
        return

    try:
        import datasets  # Windows 下先于 torch 导入，保持与训练入口一致
        from transformers import AutoTokenizer
        from dataset.lm_dataset import PretrainDataset, SFTDataset
    except ImportError as exc:
        parser.exit(1, f"\n无法查看处理结果，当前环境缺少训练依赖：{exc}\n请使用已安装项目 requirements.txt 依赖的 Python 环境。\n")

    first = samples[0]
    if isinstance(first, dict) and "text" in first:
        dataset_class = PretrainDataset
    elif isinstance(first, dict) and "conversations" in first:
        dataset_class = SFTDataset
    else:
        parser.error("处理模式目前支持 text（预训练）和 conversations（SFT）格式")

    tokenizer = AutoTokenizer.from_pretrained(str(ROOT / "model"), local_files_only=True)
    # 只加载已预览的少量样本，避免为查看数据而加载整个训练集。
    # 把少量预览样本写入临时 JSONL，复用真实 Dataset 处理逻辑；退出上下文自动清理。
    with tempfile.TemporaryDirectory(prefix="minimind_preview_") as temporary:
        preview_path = Path(temporary) / "preview.jsonl"
        preview_path.write_text(
            "\n".join(json.dumps(sample, ensure_ascii=False) for sample in samples),
            encoding="utf-8",
        )
        dataset = dataset_class(str(preview_path), tokenizer, max_length=args.max_length)
        print(f"\n使用 {dataset_class.__name__}，预览子集共 {len(dataset)} 条。")
        for index in range(len(dataset)):
            input_ids, labels = dataset[index]
            print(f"\n===== 处理后的样本 {index} =====")
            print("形状：", tuple(input_ids.shape))
            print("input_ids：", input_ids.tolist())
            print("labels：", labels.tolist())
            print("还原文本：", tokenizer.decode(input_ids.tolist()))
        print("\ninput_ids 是 token 编号；labels 中 -100 的位置不参与损失计算。")


if __name__ == "__main__":
    main()
