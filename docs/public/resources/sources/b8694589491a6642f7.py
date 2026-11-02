# 兼容 OpenAI 协议的本地聊天客户端：发送消息，读取流式增量，并保存最终回答到历史。
from openai import OpenAI

# 客户端 base_url 指向本地兼容服务；api_key 是此示例的占位配置。
client = OpenAI(
    api_key="sk-123",
    base_url="http://localhost:11434/v1"
)
stream = True
conversation_history_origin = []
conversation_history = conversation_history_origin.copy()
history_messages_num = 0  # 必须设置为偶数（Q+A），为0则不携带历史对话
while True:
    query = input('[Q]: ')
    conversation_history.append({"role": "user", "content": query})
    # 发送最近的消息片段；history_messages_num 为 0 时仅发送当前用户输入。
    response = client.chat.completions.create(
        model="minimind-local:latest",
        messages=conversation_history[-(history_messages_num or 1):],
        stream=stream,
        temperature=0.8,
        max_tokens=2048,
        top_p=0.8,
        extra_body={"chat_template_kwargs": {"open_thinking": True}, "reasoning_effort": "medium"} # 思考开关
    )
    if not stream:
        if not response.choices or response.choices[0].message is None:
            raise ValueError("LLM returned empty or filtered response")
        assistant_res = response.choices[0].message.content
        print('[A]: ', assistant_res)
    else:
        print('[A]: ', end='', flush=True)
        assistant_res = ''
        # 流式 chunk 是增量，不是完整回答；分别读取 reasoning_content 与 content 并逐步累加。
        for chunk in response:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta is None:
                continue
            r = getattr(delta, 'reasoning_content', None) or ""
            c = delta.content or ""
            if r:
                print(f'\033[90m{r}\033[0m', end="", flush=True)
            if c:
                print(c, end="", flush=True)
            # 只把最终正文写入对话历史，灰色展示的思考内容不会在此累加。
            assistant_res += c

    conversation_history.append({"role": "assistant", "content": assistant_res})
    print('\n\n')
