"""Provider-agnostic LLM layer. A provider takes (system, messages, tool_specs) and
returns {"text": str|None, "tool_calls": [{"id","name","arguments":dict}]}.

Messages use a neutral format:
  {"role":"user"|"assistant","content":str, "tool_calls":[...]}  /  {"role":"tool","tool_call_id","name","content":json}
"""
import json, os


class ScriptedProvider:
    """Replays a fixed list of responses -- used by tests so pytest needs no API key."""
    def __init__(self, responses):
        self.responses = list(responses)

    def complete(self, system, messages, tools):
        return self.responses.pop(0) if self.responses else {"text": "(scripted: no more responses)", "tool_calls": []}


class OpenAIProvider:
    def __init__(self, model=None):
        from openai import OpenAI  # pip install openai
        self.client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        self.model = model or os.getenv("PAYLANE_MODEL", "gpt-4o-mini")

    def complete(self, system, messages, tools):
        msgs = [{"role": "system", "content": system}]
        for m in messages:
            if m["role"] == "tool":
                msgs.append({"role": "tool", "tool_call_id": m["tool_call_id"], "content": m["content"]})
            elif m.get("tool_calls"):
                msgs.append({"role": "assistant", "content": m.get("content"), "tool_calls": [
                    {"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": json.dumps(c["arguments"])}}
                    for c in m["tool_calls"]]})
            else:
                msgs.append({"role": m["role"], "content": m["content"]})
        r = self.client.chat.completions.create(model=self.model, messages=msgs,
              tools=[{"type": "function", "function": t} for t in tools], temperature=0)
        msg = r.choices[0].message
        return {"text": msg.content, "tool_calls": [
            {"id": c.id, "name": c.function.name, "arguments": json.loads(c.function.arguments or "{}")}
            for c in (msg.tool_calls or [])]}


class AnthropicProvider:
    def __init__(self, model=None):
        import anthropic  # pip install anthropic
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self.model = model or os.getenv("PAYLANE_MODEL", "claude-sonnet-4-5")

    def complete(self, system, messages, tools):
        msgs = []
        for m in messages:
            if m["role"] == "tool":
                msgs.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": m["content"]}]})
            elif m.get("tool_calls"):
                blocks = ([{"type": "text", "text": m["content"]}] if m.get("content") else []) + [
                    {"type": "tool_use", "id": c["id"], "name": c["name"], "input": c["arguments"]} for c in m["tool_calls"]]
                msgs.append({"role": "assistant", "content": blocks})
            else:
                msgs.append({"role": m["role"], "content": m["content"]})
        r = self.client.messages.create(model=self.model, system=system, messages=msgs, max_tokens=1024,
              tools=[{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in tools])
        text = "".join(b.text for b in r.content if b.type == "text") or None
        return {"text": text, "tool_calls": [{"id": b.id, "name": b.name, "arguments": b.input} for b in r.content if b.type == "tool_use"]}


class OllamaProvider:
    """OpenAI-compatible local LLM via Ollama."""
    def __init__(self, model=None):
        from openai import OpenAI  # pip install openai
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        # Default to smallest Qwen with reliable tool calling
        self.model = model or os.getenv("PAYLANE_MODEL", "qwen2.5:1.5b")
        self.client = OpenAI(api_key="ollama", base_url=base_url)

    def complete(self, system, messages, tools):
        msgs = [{"role": "system", "content": system}]
        for m in messages:
            if m["role"] == "tool":
                msgs.append({"role": "tool", "tool_call_id": m["tool_call_id"], "content": m["content"]})
            elif m.get("tool_calls"):
                msgs.append({"role": "assistant", "content": m.get("content"), "tool_calls": [
                    {"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": json.dumps(c["arguments"])}}
                    for c in m["tool_calls"]]})
            else:
                msgs.append({"role": m["role"], "content": m["content"]})
        r = self.client.chat.completions.create(model=self.model, messages=msgs,
              tools=[{"type": "function", "function": t} for t in tools], temperature=0)
        msg = r.choices[0].message
        return {"text": msg.content, "tool_calls": [
            {"id": c.id, "name": c.function.name, "arguments": json.loads(c.function.arguments or "{}")}
            for c in (msg.tool_calls or [])]}


class OpenRouterProvider:
    """OpenAI-compatible API via OpenRouter with retry logic."""
    def __init__(self, model=None):
        import time
        from openai import OpenAI  # pip install openai
        self.time = time
        self.model = model or os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3.5-lightning:free")
        self.retries = int(os.getenv("OPENROUTER_RETRIES", "6"))
        self.client = OpenAI(
            api_key=os.environ.get("OPENROUTER_API_KEY", ""),
            base_url="https://openrouter.ai/api/v1"
        )

    def complete(self, system, messages, tools):
        msgs = [{"role": "system", "content": system}]
        for m in messages:
            if m["role"] == "tool":
                msgs.append({"role": "tool", "tool_call_id": m["tool_call_id"], "content": m["content"]})
            elif m.get("tool_calls"):
                msgs.append({"role": "assistant", "content": m.get("content"), "tool_calls": [
                    {"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": json.dumps(c["arguments"])}}
                    for c in m["tool_calls"]]})
            else:
                msgs.append({"role": m["role"], "content": m["content"]})
        
        # Retry with exponential backoff: 5s, 10s, 20s, 40s, 60s, 60s
        for attempt in range(self.retries):
            try:
                r = self.client.chat.completions.create(
                    model=self.model,
                    messages=msgs,
                    tools=[{"type": "function", "function": t} for t in tools],
                    temperature=0
                )
                msg = r.choices[0].message
                return {"text": msg.content, "tool_calls": [
                    {"id": c.id, "name": c.function.name, "arguments": json.loads(c.function.arguments or "{}")}
                    for c in (msg.tool_calls or [])]}
            except Exception as e:
                if attempt < self.retries - 1:
                    wait = min(5 * (2 ** attempt), 60)  # 5, 10, 20, 40, 60, 60
                    self.time.sleep(wait)
                else:
                    raise


def from_env():
    # Auto-detect OpenRouter if key is set
    if os.getenv("OPENROUTER_API_KEY") and not os.getenv("PAYLANE_PROVIDER"):
        return OpenRouterProvider()
    
    p = os.getenv("PAYLANE_PROVIDER", "openai").lower()
    return {"openai": OpenAIProvider, "anthropic": AnthropicProvider, "ollama": OllamaProvider, "openrouter": OpenRouterProvider}[p]()
