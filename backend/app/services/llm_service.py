import json

from openai import OpenAI

from app.core.config import settings

_CURRENT_YEAR = 2026


def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key or "")


def parse_hotel_query(query: str) -> dict:
    client = _client()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": f"""사용자의 자연어 숙소 검색 요청에서 다음 정보를 JSON으로 추출하세요.
연도가 없는 날짜는 {_CURRENT_YEAR}년으로 가정하세요.

출력 형식:
{{
  "destination": "도시명 영문 (기본값: Paris)",
  "checkin": "YYYY-MM-DD",
  "checkout": "YYYY-MM-DD",
  "adults": 숫자 (기본값: 2),
  "currency": "EUR|USD|KRW (기본값: KRW)",
  "preferences": ["선호 조건 리스트"]
}}

preferences 예시: ["에펠탑 근처", "역세권", "조식포함", "무료취소", "수영장", "루브르 근처"]""",
            },
            {"role": "user", "content": query},
        ],
    )
    return json.loads(response.choices[0].message.content)


def parse_flight_query(query: str) -> dict:
    client = _client()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": f"""사용자의 자연어 항공권 검색 요청에서 다음 정보를 JSON으로 추출하세요.
연도가 없는 날짜는 {_CURRENT_YEAR}년으로 가정하세요.

출력 형식:
{{
  "origin": "출발 도시 한글 또는 영문 (기본값: 서울)",
  "destination": "도착 도시 한글 또는 영문 (기본값: 파리)",
  "departure_date": "YYYY-MM-DD",
  "return_date": "YYYY-MM-DD 또는 null (편도면 null)",
  "adults": 숫자 (기본값: 1),
  "currency": "KRW|USD|EUR (기본값: KRW)",
  "preferences": ["선호 조건 리스트"]
}}

preferences 예시: ["직항", "저렴한 가격", "대한항공", "오전 출발", "수화물 포함"]""",
            },
            {"role": "user", "content": query},
        ],
    )
    return json.loads(response.choices[0].message.content)


def rank_hotels(hotels: list[dict], preferences: list[str]) -> list[dict]:
    if not hotels:
        return []
    client = _client()
    prefs_str = ", ".join(preferences) if preferences else "특별한 선호 없음"
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": """당신은 파리 여행 전문 숙소 추천 AI입니다.
호텔 목록과 사용자 선호도를 바탕으로 최대 5개를 선정하고, 결과를 다음 JSON 형식으로 반환하세요.

{
  "recommendations": [
    {
      "hotelId": "호텔ID (문자열 또는 숫자 그대로)",
      "rank": 1,
      "reason": "2~3문장, 선호도와 연결지어 구체적으로"
    }
  ]
}

추천 이유에는 선호 조건 충족 여부, 위치, 리뷰 점수, 가격 대비 가치를 언급하세요.""",
            },
            {
                "role": "user",
                "content": f"선호 조건: {prefs_str}\n\n호텔 목록:\n{json.dumps(hotels, ensure_ascii=False)}",
            },
        ],
    )
    result = json.loads(response.choices[0].message.content)
    return result.get("recommendations", [])


def rank_flights(flights: list[dict], preferences: list[str]) -> list[dict]:
    if not flights:
        return []
    client = _client()
    prefs_str = ", ".join(preferences) if preferences else "특별한 선호 없음"
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": """당신은 항공권 추천 AI입니다.
항공권 목록과 사용자 선호도를 바탕으로 최대 5개를 선정하고, 결과를 다음 JSON 형식으로 반환하세요.

{
  "recommendations": [
    {
      "flightId": "항공권ID",
      "rank": 1,
      "reason": "2~3문장, 선호도와 연결지어 구체적으로"
    }
  ]
}

추천 이유에는 선호 조건 충족 여부, 직항 여부, 가격, 소요 시간을 언급하세요.""",
            },
            {
                "role": "user",
                "content": f"선호 조건: {prefs_str}\n\n항공권 목록:\n{json.dumps(flights, ensure_ascii=False)}",
            },
        ],
    )
    result = json.loads(response.choices[0].message.content)
    return result.get("recommendations", [])
