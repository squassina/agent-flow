import ast
import operator as op

_OPS = {
    ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv,
    ast.FloorDiv: op.floordiv, ast.Mod: op.mod, ast.Pow: op.pow,
    ast.USub: op.neg, ast.UAdd: op.pos,
}


def _eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ValueError("expoente muito grande")
        return _OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    raise ValueError("expressão não permitida")


def tool_calculator(expression: str) -> str:
    try:
        return str(_eval(ast.parse(expression, mode="eval").body))
    except Exception as e:
        return f"Erro no cálculo: {e}"


def tool_web_search(query: str) -> str:
    try:
        from ddgs import DDGS
        results = DDGS().text(query, max_results=5)
        if not results:
            return "Nenhum resultado encontrado."
        return "\n".join(f"- {r['title']}: {r['body']} ({r['href']})" for r in results)
    except Exception as e:
        return f"Erro na busca: {e}"


AVAILABLE_TOOLS = {
    "calculator": {
        "function": tool_calculator,
        "schema": {"type": "function", "function": {
            "name": "calculator",
            "description": "Executa cálculos matemáticos (+, -, *, /, //, %, **).",
            "parameters": {"type": "object",
                           "properties": {"expression": {"type": "string", "description": "Ex: 2 + 2 * 3"}},
                           "required": ["expression"]}}},
    },
    "web_search": {
        "function": tool_web_search,
        "schema": {"type": "function", "function": {
            "name": "web_search",
            "description": "Pesquisa informações atualizadas na web.",
            "parameters": {"type": "object",
                           "properties": {"query": {"type": "string", "description": "Termo de busca"}},
                           "required": ["query"]}}},
    },
}
