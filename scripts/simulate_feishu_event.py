import argparse
import json
import urllib.request


def build_event(text: str, token: str):
    return {
        "schema": "2.0",
        "header": {
            "event_id": "local_evt_1",
            "event_type": "im.message.receive_v1",
            "tenant_key": "local_tenant",
            "token": token,
        },
        "event": {
            "sender": {"sender_id": {"open_id": "local_user"}},
            "message": {
                "message_id": "local_message",
                "chat_id": "local_chat",
                "chat_type": "p2p",
                "message_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Send a local Feishu-like event to the gateway.")
    parser.add_argument("text", nargs="?", default="帮我查一下2024年以来人机协同的论文")
    parser.add_argument("--url", default="http://127.0.0.1:8080/integrations/feishu/events")
    parser.add_argument("--token", default="")
    parser.add_argument("--print-only", action="store_true")
    args = parser.parse_args()

    payload = build_event(args.text, args.token)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if args.print_only:
        print(body.decode("utf-8"))
        return
    req = urllib.request.Request(args.url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        print(resp.read().decode("utf-8"))


if __name__ == "__main__":
    main()
