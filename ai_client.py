import base64
import json
import requests


_SYSTEM_PROMPT = """你是一个音频元数据提取专家。请根据用户提供的文本和/或图片，提取音频专辑的元数据。

请严格按以下 key=value 格式输出（不要输出任何其他内容）：

artist=专辑艺术家
title=专辑标题
year=发行年份
numtracks=曲目总数
disc_id=MusicBrainz disc ID（如有）
catalog_id=品番/目录编号（如有）
0=第1轨曲名
0artist=第1轨艺术家（仅当与专辑艺术家不同时）
1=第2轨曲名
1artist=第2轨艺术家
...以此类推

规则：
- 曲目编号从 0 开始
- 每轨必须包含标题，轨艺术家可选
- 年份为 4 位数字
- 如果无法确定某个字段，直接留空，不要填写 Unknown 或猜测值
- 轨艺术家(0artist/1artist/...)仅限 Vocal/歌手，除非明确指明是作曲/编曲等其他角色
- 如果信息来自图片，尽可能完整提取"""


def call(endpoint: str, token: str, model: str,
         text: str = '', images: list[bytes] | None = None) -> str:
    if not token:
        raise ValueError('API token 未设置')

    print(f'[AI] 正在调用 {model}...')
    url = endpoint.rstrip('/') + '/chat/completions'

    user_content: list[dict] = []
    if images:
        for img in images:
            b64 = base64.b64encode(img).decode('ascii')
            user_content.append({
                'type': 'image_url',
                'image_url': {'url': f'data:image/jpeg;base64,{b64}'},
            })
    if text:
        user_content.append({'type': 'text', 'text': text})

    body = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': _SYSTEM_PROMPT},
            {'role': 'user', 'content': user_content if images else text},
        ],
        'temperature': 0.3,
        'max_tokens': 4096,
    }

    resp = requests.post(
        url,
        headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        },
        json=body,
        timeout=120,
    )

    if resp.status_code != 200:
        raise requests.RequestException(
            f'API 返回 {resp.status_code}: {resp.text[:500]}'
        )

    data = resp.json()
    try:
        return data['choices'][0]['message']['content']
    except (KeyError, IndexError) as e:
        raise requests.RequestException(
            f'API 响应格式异常: {json.dumps(data, ensure_ascii=False)[:500]}'
        ) from e
