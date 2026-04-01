from app.tools.basic_tools import get_time, get_weather_mock

TOOLS = {
    "get_time": get_time,
    "get_weather_mock": get_weather_mock,
}

TOOL_SCHEMAS = {
    "get_time": {
        "name": "get_time",
        "description": "返回当前本地时间",
        "args": {},
    },
    "get_weather_mock": {
        "name": "get_weather_mock",
        "description": "根据城市名返回 mock 天气",
        "args": {
            "city": "string"
        },
    },
}
