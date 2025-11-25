import os
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage


def main():
    base_url = os.getenv("LITELLM_BASE_URL", "http://8.153.71.199:4000/")
    api_key = os.getenv("LITELLM_API_KEY")
    model = os.getenv("LITELLM_MODEL", "gemini/gemini-2.5-flash")

    if not api_key:
        raise RuntimeError("请先在环境变量中设置 LITELLM_API_KEY")

    # llm = ChatOpenAI(
    #     model=model,
    #     base_url=base_url.rstrip("/"),
    #     api_key=api_key,
    #     temperature=0.2,
    #     max_tokens=1024,
    # )
    llm = ChatOpenAI(
        temperature=0.1,
        model=model,
        openai_api_key=api_key,
        openai_api_base=base_url,
        max_tokens=4096
    )


    system_prompt = (
        "You are an assistant that summarizes Slack conversations. "
        "Highlight decisions, blockers, and next steps."
    )

    transcript = """Summarize the following Slack thread.
Return a concise bullet list of the key points, decisions, and follow-ups.

Conversation:

- (1762313632.351149) U09Q6RLQFCG: 我们来讨论一下用户相关的需求
- (1762313765.384139) U09Q6RLQFCG: <@U09PG47C6AY> 在这里讨论
- (1762313785.880109) U09PG47C6AY: 在没有身份证号码的情况下，用户应该以邮箱地址区分还是以手机号区分？
- (1762313798.215589) U09Q6RLQFCG: 国内的话用手机号最合理吧
- (1762313821.558819) U09Q6RLQFCG: 用户需要哪些字段？姓名性别，出生年月
- (1762313824.662319) U09Q6RLQFCG: 还有什么？
- (1762313899.514329) U09PG47C6AY: 一些联系方式，比如手机号、邮箱地址，
"""

    print("=== Request ===")
    print("Model:", model)
    print("System prompt:", system_prompt)
    print("User transcript:", transcript)

    resp = llm.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=transcript),
        ]
    )

    print("\n=== LangChain ChatOpenAI raw ===")
    print(repr(resp))

    print("\n=== Parsed content ===")
    print("type(resp.content):", type(resp.content))
    print("content:", resp.content)


if __name__ == "__main__":
    main()