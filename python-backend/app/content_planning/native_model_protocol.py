"""Pure protocol conversion for the bank's doubaoNative text endpoint.

No network, credentials, database access or module startup side effects.
The rest of the algorithm continues to consume a Chat Completions shaped result.
"""
from copy import deepcopy


class NativeProtocolError(ValueError):
    """Only fixed, non-provider messages may leave this boundary."""


def request_body(payload):
    messages = payload.get('messages')
    if not isinstance(messages, list) or not messages:
        raise NativeProtocolError('行内模型请求缺少消息列表')
    items = []
    for message in messages:
        if (not isinstance(message, dict)
                or message.get('role') not in ('system', 'user', 'assistant')
                or not isinstance(message.get('content'), str)):
            raise NativeProtocolError('行内文本模型仅支持 system/user/assistant 文本消息')
        items.append({'role': message['role'], 'type': 'message', 'content': message['content']})
    if payload.get('stream') not in (None, False):
        raise NativeProtocolError('当前策划算法仅支持非流式模型响应')
    body = {'model': payload['model'], 'input': items, 'stream': False}
    for name in ('temperature', 'thinking', 'top_p'):
        if name in payload:
            body[name] = deepcopy(payload[name])
    if 'max_tokens' in payload:
        body['max_output_tokens'] = payload['max_tokens']
    output = payload.get('response_format', {'type': 'json_object'})
    if output.get('type') == 'json_schema':
        schema = output.get('json_schema')
        if (not isinstance(schema, dict) or not isinstance(schema.get('schema'), dict)
                or not schema.get('name')):
            raise NativeProtocolError('行内模型 JSON Schema 配置不完整')
        body['text'] = {'format': {'type': 'json_schema', 'strict': True,
                                   'name': schema['name'], 'schema': deepcopy(schema['schema'])}}
    elif output.get('type') == 'json_object':
        body['text'] = {'format': {'type': 'json_object'}}
    else:
        raise NativeProtocolError('行内模型输出格式不受支持')
    return body


def completion_result(result):
    """Consume original Responses JSON only; never guess a code/data envelope.

    Host-specific envelopes can be implemented via PlanningDependencies.model_adapters.
    Reasoning output is ignored and is never included in the algorithm's JSON text.
    """
    if not isinstance(result, dict) or result.get('status') != 'completed' or result.get('error'):
        raise NativeProtocolError('行内模型响应未正常完成或协议不匹配')
    output = result.get('output')
    if not isinstance(output, list):
        raise NativeProtocolError('行内模型响应缺少输出列表')
    messages = []
    for item in output:
        if not isinstance(item, dict):
            raise NativeProtocolError('行内模型输出列表格式无效')
        if item.get('type') == 'reasoning':
            continue
        if item.get('type') != 'message' or item.get('role') != 'assistant':
            raise NativeProtocolError('行内模型返回了不支持的输出类型')
        if item.get('status', 'completed') != 'completed' or not isinstance(item.get('content'), list):
            raise NativeProtocolError('行内模型消息未完成')
        chunks = []
        for part in item['content']:
            if (not isinstance(part, dict) or part.get('type') != 'output_text'
                    or not isinstance(part.get('text'), str)):
                raise NativeProtocolError('行内模型拒绝输出或文本格式无效')
            chunks.append(part['text'])
        messages.append(''.join(chunks))
    if len(messages) != 1 or not messages[0].strip():
        raise NativeProtocolError('行内模型必须返回一条完整的助手消息')
    normalized = {'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': messages[0]}}]}
    for name in ('id', 'model'):
        if name in result:
            normalized[name] = result[name]
    if 'usage' in result:
        # Keep exact provider Token measurements, including any reasoning details.
        normalized['usage'] = deepcopy(result['usage'])
    return normalized
