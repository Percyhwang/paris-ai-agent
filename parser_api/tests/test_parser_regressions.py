import io
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from parser_api.parsers.create_plan.parser import parse_create_plan
from parser_api.parsers.modify_plan.parser import parse_modify_plan


CREATE_CASES = [
    {
        "name": "basic_nights_days",
        "message": "파리 3박4일 여행 계획 세워줘",
        "expected": {"dates": {"days": 4, "source": "explicit"}, "clarify": {"needed": False}},
    },
    {
        "name": "basic_days_only",
        "message": "파리 5일 코스 구성해줘",
        "expected": {"dates": {"days": 5, "source": "explicit"}},
    },
    {
        "name": "date_range_month_same",
        "message": "7월23일부터26일까지 파리 일정 짜줘",
        "expected": {
            "dates": {"start_date": "2026-07-23", "end_date": "2026-07-26", "days": 4, "source": "explicit"}
        },
    },
    {
        "name": "date_range_year_full",
        "message": "2026년7월23일~2026년7월26일 파리 여행 계획 세워줘",
        "expected": {
            "dates": {"start_date": "2026-07-23", "end_date": "2026-07-26", "days": 4, "source": "explicit"}
        },
    },
    {
        "name": "date_range_month_to_day",
        "message": "7월23일~26일 파리 여행 계획 세워줘",
        "expected": {
            "dates": {"start_date": "2026-07-23", "end_date": "2026-07-26", "days": 4, "source": "explicit"}
        },
    },
    {
        "name": "missing_days_asks",
        "message": "파리 여행 일정 짜줘",
        "expected": {"dates": {"days": None, "source": "missing"}, "clarify": {"needed": True, "missing_fields": ["dates.days"]}},
    },
    {
        "name": "solo_trip",
        "message": "혼자 파리 3박4일 여행 계획 세워줘",
        "expected": {"party": {"adult": 1, "trip_style": "solo"}},
    },
    {
        "name": "couple_trip",
        "message": "커플 파리 3박4일 여행 짜줘",
        "expected": {"party": {"adult": 2, "trip_style": "couple"}},
    },
    {
        "name": "girlfriend_trip",
        "message": "여자친구랑 파리 4일 여행 짜줘",
        "expected": {"party": {"adult": 2, "trip_style": "couple"}},
    },
    {
        "name": "romantic_night_view_prompt",
        "message": "여자친구랑 파리 3박4일 가는데 로맨틱하게 짜줘. 브런치 하나 넣고 저녁 야경이 예쁘면 좋겠어. 너무 빡세지 않게.",
        "expected": {
            "party": {"adult": 2, "trip_style": "couple"},
            "pace": {"level": "slow"},
            "preferences": {
                "themes": ["romance", "night_view"],
                "meal_preference": ["brunch"],
                "night_view_required": True,
            },
        },
    },
    {
        "name": "friends_digit_count",
        "message": "친구 3명이서 파리 4일 일정 빡세게 짜줘",
        "expected": {"party": {"adult": 3, "trip_style": "friends"}, "pace": {"level": "fast"}},
    },
    {
        "name": "friends_korean_count",
        "message": "친구 둘이 파리 4일 일정 짜줘",
        "expected": {"party": {"adult": 2, "trip_style": "friends"}},
    },
    {
        "name": "friends_plural_transit_memorable",
        "message": "7월3일부터 11일까지 친구들이랑 파리러로 여행을 가는데 대중교통을 이용할거야 기억에 남는 파리 여행 계획 만들어줘",
        "expected": {
            "dates": {"start_date": "2026-07-03", "end_date": "2026-07-11", "days": 9},
            "party": {"adult": 3, "trip_style": "friends"},
            "mobility": {"travel_mode": "transit"},
            "preferences": {"themes": ["landmark", "photo"]},
        },
    },
    {
        "name": "parents_trip",
        "message": "부모님이랑 5일 여행 짜줘",
        "expected": {"party": {"adult": 3, "trip_style": "family"}},
    },
    {
        "name": "mother_trip",
        "message": "엄마랑 4박5일 일정 짜줘",
        "expected": {"party": {"adult": 2, "trip_style": "family"}},
    },
    {
        "name": "father_trip",
        "message": "아빠랑 2박3일 계획 짜줘",
        "expected": {"party": {"adult": 2, "trip_style": "family"}},
    },
    {
        "name": "child_family_trip",
        "message": "아이랑 가족여행 3박4일 일정 짜줘",
        "expected": {"party": {"adult": 1, "elementary": 1, "trip_style": "family"}, "preferences": {"themes": ["family"]}},
    },
    {
        "name": "two_children_trip",
        "message": "아이 2명이랑 파리 4일 여행 짜줘",
        "expected": {"party": {"adult": 1, "elementary": 2, "trip_style": "family"}},
    },
    {
        "name": "stroller_indoor",
        "message": "유모차 끌고 갈거라 실내 위주로 3박4일 짜줘",
        "expected": {"mobility": {"stroller": True}, "constraints": {"indoor_focus": True}},
    },
    {
        "name": "wheelchair_trip",
        "message": "휠체어 사용해서 2박3일 일정 짜줘",
        "expected": {"mobility": {"wheelchair": True}},
    },
    {
        "name": "rainy_plan",
        "message": "비 오면 대체 일정도 같이 짜줘 3박4일로",
        "expected": {"constraints": {"rainy_plan": True}},
    },
    {
        "name": "indoor_and_rainy",
        "message": "실내 위주, 비 오면 대체 일정도 있는 3박4일 여행 짜줘",
        "expected": {"constraints": {"indoor_focus": True, "rainy_plan": True}},
    },
    {
        "name": "cafe_weight",
        "message": "카페 많이 가고 4일 일정 짜줘",
        "expected": {"preferences": {"weights": {"cafe": 0.8, "museum": 0.3}}},
    },
    {
        "name": "shopping_weight",
        "message": "쇼핑 위주로 3일 일정 짜줘",
        "expected": {"preferences": {"weights": {"shopping": 0.8}}},
    },
    {
        "name": "shopping_plain_interest",
        "message": "쇼핑이랑 랜드마크 둘 다 챙기고 싶어",
        "expected": {"preferences": {"themes": ["shopping", "landmark"], "weights": {"shopping": 0.8}}},
    },
    {
        "name": "night_view_weight",
        "message": "야경 위주로 3박4일 일정 짜줘",
        "expected": {"preferences": {"weights": {"night_view": 0.8}}},
    },
    {
        "name": "avoid_nightlife_does_not_force_night_slot",
        "message": "부모님이랑 가는 파리 여행이라 많이 걷지 않는 일정으로 짜줘. 야간 유흥은 빼고 쉬엄쉬엄 보고 싶어.",
        "expected": {
            "party": {"trip_style": "family"},
            "pace": {"level": "slow"},
            "preferences": {"preferred_time_slots": []},
        },
    },
    {
        "name": "museum_limit",
        "message": "박물관은 하루 1개만 가고 싶어 4일 일정으로 짜줘",
        "expected": {"constraints": {"museum_per_day": 1}},
    },
    {
        "name": "museum_limit_two",
        "message": "미술관 하루 2개만 가는 5일 일정으로 짜줘",
        "expected": {"constraints": {"museum_per_day": 2}},
    },
    {
        "name": "walk_limit_numeric",
        "message": "하루 7km 이하로 걷고 싶어 3박4일 일정 짜줘",
        "expected": {"mobility": {"max_walk_km_per_day": 7}},
    },
    {
        "name": "walk_limit_soft",
        "message": "걷기는 적게 하고 싶은 4일 일정 짜줘",
        "expected": {"mobility": {"max_walk_km_per_day": 5, "travel_mode": "transit"}},
    },
    {
        "name": "walk_mode",
        "message": "도보 위주로 3일 일정 짜줘",
        "expected": {"mobility": {"travel_mode": "walk"}},
    },
    {
        "name": "transit_mode",
        "message": "대중교통 위주로 2박3일 일정 짜줘",
        "expected": {"mobility": {"travel_mode": "transit"}},
    },
    {
        "name": "min_transfers",
        "message": "환승 적게 다니는 2박3일 일정 짜줘",
        "expected": {"mobility": {"optimize": "min_transfers"}},
    },
    {
        "name": "transit_and_min_transfers",
        "message": "대중교통 위주로 환승 적게 다니고 싶어 2박3일 여행 계획 세워줘",
        "expected": {"mobility": {"travel_mode": "transit", "optimize": "min_transfers"}},
    },
    {
        "name": "must_include_place",
        "message": "에펠탑은 꼭 넣고 3박4일 일정 짜줘",
        "expected": {"preferences": {"must_include": ["에펠탑"]}},
    },
    {
        "name": "must_avoid_place",
        "message": "루브르는 빼줘 3박4일 일정 짜줘",
        "expected": {"preferences": {"must_avoid": ["루브르"]}},
    },
    {
        "name": "include_and_avoid",
        "message": "에펠탑은 꼭 넣고 루브르는 빼줘 3박4일 일정 짜줘",
        "expected": {"preferences": {"must_include": ["에펠탑"], "must_avoid": ["루브르"]}},
    },
    {
        "name": "filial_trip",
        "message": "효도여행으로 4박5일 짜줘",
        "expected": {"party": {"trip_style": "family"}, "preferences": {"themes": ["family"]}},
    },
    {
        "name": "family_trip_theme",
        "message": "가족여행 4일 일정 짜줘",
        "expected": {"party": {"trip_style": "family"}, "preferences": {"themes": ["family"]}},
    },
    {
        "name": "romance_trip_theme",
        "message": "로맨스 여행 4일 일정 짜줘",
        "expected": {"party": {"trip_style": "couple"}, "preferences": {"themes": ["romance"]}},
    },
    {
        "name": "honeymoon_trip",
        "message": "신혼여행으로 5일 일정 짜줘",
        "expected": {"party": {"trip_style": "couple"}, "preferences": {"themes": ["romance"]}},
    },
    {
        "name": "adult_digit_count",
        "message": "성인 2명 파리 3박4일 여행 짜줘",
        "expected": {"party": {"adult": 2}},
    },
    {
        "name": "total_people_digit",
        "message": "총 4명 파리 3박4일 여행 짜줘",
        "expected": {"party": {"adult": 4}},
    },
    {
        "name": "total_people_korean",
        "message": "두 명이서 파리 3박4일 여행 짜줘",
        "expected": {"party": {"adult": 2}},
    },
    {
        "name": "adult_and_elementary",
        "message": "성인 2명, 초등학생 1명 파리 3박4일 짜줘",
        "expected": {"party": {"adult": 2, "elementary": 1}},
    },
    {
        "name": "toddler_family",
        "message": "아기 1명 포함 가족여행 3박4일 짜줘",
        "expected": {"party": {"toddler": 1, "trip_style": "family"}},
    },
    {
        "name": "children_plural",
        "message": "아이들 2명 데리고 4일 가족여행 짜줘",
        "expected": {"party": {"elementary": 2, "trip_style": "family"}, "preferences": {"themes": ["family"]}},
    },
    {
        "name": "stroller_rainy",
        "message": "유모차 끌고 가고 비 오면 대체 일정 있는 4일 계획 짜줘",
        "expected": {"mobility": {"stroller": True}, "constraints": {"rainy_plan": True}},
    },
    {
        "name": "wheelchair_transit",
        "message": "휠체어라 대중교통 위주 3일 일정 짜줘",
        "expected": {"mobility": {"wheelchair": True, "travel_mode": "transit"}},
    },
    {
        "name": "cafe_and_shopping",
        "message": "카페 많이 가고 쇼핑 위주로 4일 일정 짜줘",
        "expected": {"preferences": {"weights": {"cafe": 0.8, "shopping": 0.8}}},
    },
    {
        "name": "night_view_phrase",
        "message": "야경 많이 보고 싶어 3일 여행 짜줘",
        "expected": {"preferences": {"weights": {"night_view": 0.8}}},
    },
    {
        "name": "must_include_include_phrase",
        "message": "에펠탑 포함해서 4일 일정 짜줘",
        "expected": {"preferences": {"must_include": ["에펠탑"]}},
    },
    {
        "name": "must_include_go_phrase",
        "message": "노트르담 가고 싶고 4일 일정 짜줘",
        "expected": {"preferences": {"must_include": ["노트르담"]}},
    },
    {
        "name": "must_avoid_exclude_phrase",
        "message": "베르사유는 제외하고 3박4일 일정 짜줘",
        "expected": {"preferences": {"must_avoid": ["베르사유"]}},
    },
    {
        "name": "family_low_walk",
        "message": "부모님 모시고 5일 여행 짜줘 걷기는 적게",
        "expected": {"party": {"trip_style": "family"}, "mobility": {"max_walk_km_per_day": 5, "travel_mode": "transit"}},
    },
    {
        "name": "activity_theme",
        "message": "액티비티 위주로 파리 4일 일정 짜줘",
        "expected": {"preferences": {"themes": ["activity"]}},
    },
    {
        "name": "history_theme",
        "message": "역사 투어 위주로 파리 3박4일 짜줘",
        "expected": {"preferences": {"themes": ["history"]}},
    },
    {
        "name": "museum_theme",
        "message": "미술관 위주로 4일 여행 짜줘",
        "expected": {"preferences": {"themes": ["museum"], "weights": {"museum": 0.85}}},
    },
    {
        "name": "museum_plain_interest",
        "message": "박물관 좋아해서 파리 3일 일정 짜줘",
        "expected": {"preferences": {"themes": ["museum"], "weights": {"museum": 0.85}}},
    },
    {
        "name": "art_theme",
        "message": "예술 감성 아트 투어 중심으로 4일 일정 짜줘",
        "expected": {"preferences": {"themes": ["art"], "weights": {"museum": 0.75}}},
    },
    {
        "name": "architecture_theme",
        "message": "건축 투어 위주로 3일 일정 짜줘",
        "expected": {"preferences": {"themes": ["architecture"]}},
    },
    {
        "name": "foodie_theme",
        "message": "맛집 투어 위주로 3박4일 짜줘",
        "expected": {"preferences": {"themes": ["foodie"]}},
    },
    {
        "name": "nature_theme",
        "message": "공원 피크닉 위주로 3일 일정 짜줘",
        "expected": {"preferences": {"themes": ["nature"], "weights": {"park": 0.8}}},
    },
    {
        "name": "healing_theme",
        "message": "힐링 여행으로 4일 일정 짜줘",
        "expected": {"preferences": {"themes": ["healing"]}},
    },
    {
        "name": "local_theme",
        "message": "로컬 감성 위주로 3일 일정 짜줘",
        "expected": {"preferences": {"themes": ["local"]}},
    },
    {
        "name": "hidden_gems_theme",
        "message": "숨은 명소 위주로 4일 일정 짜줘",
        "expected": {"preferences": {"themes": ["hidden_gems"]}},
    },
    {
        "name": "photo_theme",
        "message": "인생샷 포토스팟 위주로 3일 일정 짜줘",
        "expected": {"preferences": {"themes": ["photo"]}},
    },
    {
        "name": "luxury_theme",
        "message": "럭셔리하게 3박4일 계획 짜줘",
        "expected": {"preferences": {"themes": ["luxury"]}, "budget": {"budget_mode": "flex"}},
    },
    {
        "name": "budget_theme",
        "message": "가성비 위주로 알뜰하게 3박4일 계획 짜줘",
        "expected": {"preferences": {"themes": ["budget"]}, "budget": {"budget_mode": "save"}},
    },
    {
        "name": "landmark_theme",
        "message": "랜드마크 위주로 2박3일 일정 짜줘",
        "expected": {"preferences": {"themes": ["landmark"]}},
    },
    {
        "name": "culture_theme",
        "message": "뮤지컬 공연 중심 문화예술 여행 3일 일정 짜줘",
        "expected": {"preferences": {"themes": ["culture"]}},
    },
    {
        "name": "history_and_museum_themes",
        "message": "역사 투어랑 미술관 위주로 파리 4일 일정 짜줘",
        "expected": {"preferences": {"themes": ["history", "museum"], "weights": {"museum": 0.85}}},
    },
]

CREATE_CASES.extend(
    [
        {
            "name": "adult_and_elementary_korean_counts",
            "message": "성인 두 명, 초등학생 한 명 파리 3박4일 짜줘",
            "expected": {"party": {"adult": 2, "elementary": 1}},
        },
        {
            "name": "adult_and_highschool_korean_counts",
            "message": "성인 두 명, 고등학생 한 명 파리 4일 일정 짜줘",
            "expected": {"party": {"adult": 2, "highschool": 1}},
        },
        {
            "name": "adult_and_middleschool_korean_counts",
            "message": "성인 두 명, 중학생 두 명 5일 일정 짜줘",
            "expected": {"party": {"adult": 2, "middleschool": 2}},
        },
        {
            "name": "toddler_korean_count",
            "message": "아기 한 명 포함 가족여행 3박4일 짜줘",
            "expected": {"party": {"adult": 1, "toddler": 1, "trip_style": "family"}},
        },
        {
            "name": "mixed_family_korean_counts",
            "message": "성인 두 명, 초등학생 두 명, 아기 한 명 포함 4박5일 짜줘",
            "expected": {"party": {"adult": 2, "elementary": 2, "toddler": 1}},
        },
        {
            "name": "museum_limit_korean_two",
            "message": "박물관 하루 두 개만 가는 4일 일정 짜줘",
            "expected": {"constraints": {"museum_per_day": 2}},
        },
        {
            "name": "museum_limit_korean_one",
            "message": "미술관 하루 한 개만 보는 3박4일 짜줘",
            "expected": {"constraints": {"museum_per_day": 1}},
        },
        {
            "name": "pace_slow_chuncheonhi",
            "message": "천천히 4일 일정 짜줘",
            "expected": {"pace": {"level": "slow"}},
        },
        {
            "name": "pace_slow_shieom",
            "message": "쉬엄쉬엄 4일 일정 짜줘",
            "expected": {"pace": {"level": "slow"}},
        },
        {
            "name": "pace_fast_tight",
            "message": "타이트하게 3박4일 짜줘",
            "expected": {"pace": {"level": "fast"}},
        },
        {
            "name": "pace_fast_dense",
            "message": "빽빽하게 2박3일 일정 짜줘",
            "expected": {"pace": {"level": "fast"}},
        },
        {
            "name": "transit_subway_mode",
            "message": "지하철 위주로 3박4일 여행 짜줘",
            "expected": {"mobility": {"travel_mode": "transit"}},
        },
        {
            "name": "walk_mode_gulreoseo",
            "message": "걸어서 다니는 3일 일정 짜줘",
            "expected": {"mobility": {"travel_mode": "walk"}},
        },
        {
            "name": "min_transfers_phrase_variant",
            "message": "환승은 최소로 3일 일정 짜줘",
            "expected": {"mobility": {"optimize": "min_transfers"}},
        },
        {
            "name": "indoor_only_phrase",
            "message": "실내로만 3박4일 여행 짜줘",
            "expected": {"constraints": {"indoor_focus": True}},
        },
        {
            "name": "rainy_uchunsi_phrase",
            "message": "우천 시 대체 일정도 있는 3박4일 여행 짜줘",
            "expected": {"constraints": {"rainy_plan": True}},
        },
        {
            "name": "photo_theme_many_pictures",
            "message": "사진 많이 남기고 싶은 3일 일정 짜줘",
            "expected": {"preferences": {"themes": ["photo"]}},
        },
        {
            "name": "photo_theme_spots",
            "message": "포토 스팟 많이 가는 3일 일정 짜줘",
            "expected": {"preferences": {"themes": ["photo"]}},
        },
        {
            "name": "foodie_theme_bakery",
            "message": "빵지순례 위주로 3박4일 짜줘",
            "expected": {"preferences": {"themes": ["foodie"]}},
        },
        {
            "name": "culture_theme_opera",
            "message": "오페라랑 공연 중심으로 3일 일정 짜줘",
            "expected": {"preferences": {"themes": ["culture"]}},
        },
        {
            "name": "architecture_theme_buildings",
            "message": "건축물 구경 위주로 3일 일정 짜줘",
            "expected": {"preferences": {"themes": ["architecture"]}},
        },
        {
            "name": "history_theme_historic_sites",
            "message": "유적지 중심 역사적인 4일 일정 짜줘",
            "expected": {"preferences": {"themes": ["history"]}},
        },
        {
            "name": "hidden_gems_theme_unknown_places",
            "message": "잘 안 알려진 곳 위주로 4일 일정 짜줘",
            "expected": {"preferences": {"themes": ["hidden_gems"]}},
        },
        {
            "name": "local_theme_neighbor_feel",
            "message": "현지인 동네 느낌으로 3일 일정 짜줘",
            "expected": {"preferences": {"themes": ["local"]}},
        },
        {
            "name": "must_avoid_not_go_phrase",
            "message": "루브르는 안 가고 싶어 3박4일 일정 짜줘",
            "expected": {"preferences": {"must_avoid": ["루브르"]}},
        },
    ]
)


MODIFY_CASES = [
    {
        "name": "add_cafe_one",
        "message": "3일차 카페 하나 추가해줘",
        "expected": {"operations": [{"op": "add", "target_day": 3, "category": "cafe", "quantity": 1}], "clarify": {"needed": False}},
    },
    {
        "name": "add_restaurant_lunch",
        "message": "2일차 점심 식당 하나 추가해줘",
        "expected": {"operations": [{"op": "add", "target_day": 2, "target_slot": "lunch", "category": "restaurant", "quantity": 1}]},
    },
    {
        "name": "add_night_view_dinner",
        "message": "4일차 저녁에 야경 명소 하나 추가해줘",
        "expected": {"operations": [{"op": "add", "target_day": 4, "target_slot": "dinner", "category": "night_view", "quantity": 1}]},
    },
    {
        "name": "add_park",
        "message": "1일차 공원 하나 추가해줘",
        "expected": {"operations": [{"op": "add", "target_day": 1, "category": "park", "quantity": 1}]},
    },
    {
        "name": "add_shopping",
        "message": "3일차 쇼핑 하나 추가해줘",
        "expected": {"operations": [{"op": "add", "target_day": 3, "category": "shopping", "quantity": 1}]},
    },
    {
        "name": "add_cafe_two",
        "message": "3일차 카페 두 개 추가해줘",
        "expected": {"operations": [{"op": "add", "target_day": 3, "category": "cafe", "quantity": 2}]},
    },
    {
        "name": "remove_restaurant_lunch",
        "message": "3일차 점심 식당 빼줘",
        "expected": {"operations": [{"op": "remove", "target_day": 3, "target_slot": "lunch", "category": "restaurant"}]},
    },
    {
        "name": "remove_cafe_day",
        "message": "2일차 카페 빼줘",
        "expected": {"operations": [{"op": "remove", "target_day": 2, "category": "cafe"}]},
    },
    {
        "name": "remove_place_name",
        "message": "루브르 빼줘",
        "expected": {"operations": [{"op": "remove", "place_name": "루브르"}], "clarify": {"needed": False}},
    },
    {
        "name": "replace_place_to_place",
        "message": "루브르 대신 오르세로 바꿔줘",
        "expected": {"operations": [{"op": "replace", "place_name": "루브르", "constraints_patch": {"replace_mode": "place_to_place", "from_place": "루브르", "to_place": "오르세"}}]},
    },
    {
        "name": "replace_place_to_place_day",
        "message": "2일차 에펠탑 대신 몽마르트 넣어줘",
        "expected": {"operations": [{"op": "replace", "target_day": 2, "place_name": "에펠탑", "constraints_patch": {"replace_mode": "place_to_place", "to_place": "몽마르트"}}]},
    },
    {
        "name": "replace_place_to_category",
        "message": "루브르 말고 카페 넣어줘",
        "expected": {"operations": [{"op": "replace", "place_name": "루브르", "category": "cafe", "constraints_patch": {"replace_mode": "place_to_category", "to_category": "cafe"}}]},
    },
    {
        "name": "set_pace_slow_relaxed",
        "message": "일정 좀 여유롭게 바꿔줘",
        "expected": {"operations": [{"op": "set_pace", "pace": "slow"}]},
    },
    {
        "name": "set_pace_slow_generous",
        "message": "일정 좀 넉넉하게 바꿔줘",
        "expected": {"operations": [{"op": "set_pace", "pace": "slow"}]},
    },
    {
        "name": "set_pace_fast",
        "message": "일정 더 빡세게 바꿔줘",
        "expected": {"operations": [{"op": "set_pace", "pace": "fast"}]},
    },
    {
        "name": "set_mobility_walk",
        "message": "도보 위주로 수정해줘",
        "expected": {"operations": [{"op": "set_mobility", "mobility": {"travel_mode": "walk"}}]},
    },
    {
        "name": "set_mobility_transit",
        "message": "대중교통 위주로 바꿔줘",
        "expected": {"operations": [{"op": "set_mobility", "mobility": {"travel_mode": "transit"}}]},
    },
    {
        "name": "set_mobility_min_transfers",
        "message": "환승 적게 하도록 수정해줘",
        "expected": {"operations": [{"op": "set_mobility", "mobility": {"optimize": "min_transfers"}}]},
    },
    {
        "name": "set_mobility_walk_and_transfers",
        "message": "도보 위주로 환승 적게 수정해줘",
        "expected": {"operations": [{"op": "set_mobility", "mobility": {"travel_mode": "walk", "optimize": "min_transfers"}}]},
    },
    {
        "name": "set_mobility_wheelchair",
        "message": "휠체어 가능하게 수정해줘",
        "expected": {"operations": [{"op": "set_mobility", "mobility": {"wheelchair": True}}]},
    },
    {
        "name": "set_mobility_stroller",
        "message": "유모차 가능하게 바꿔줘",
        "expected": {"operations": [{"op": "set_mobility", "mobility": {"stroller": True}}]},
    },
    {
        "name": "set_mobility_walk_limit_numeric",
        "message": "하루 5km 이하로 걷게 수정해줘",
        "expected": {"operations": [{"op": "set_mobility", "mobility": {"max_walk_km_per_day": 5}}]},
    },
    {
        "name": "set_mobility_walk_limit_soft",
        "message": "걷기는 적게 수정해줘",
        "expected": {"operations": [{"op": "set_mobility", "mobility": {"max_walk_km_per_day": 5, "travel_mode": "transit"}}]},
    },
    {
        "name": "set_quantity_digits",
        "message": "카페를 2개에서 1개로 줄여줘",
        "expected": {"operations": [{"op": "set_quantity", "category": "cafe", "from_quantity": 2, "to_quantity": 1}], "clarify": {"needed": False}},
    },
    {
        "name": "set_quantity_korean",
        "message": "카페를 두 개에서 한 개로 줄여줘",
        "expected": {"operations": [{"op": "set_quantity", "category": "cafe", "from_quantity": 2, "to_quantity": 1}]},
    },
    {
        "name": "set_quantity_shopping",
        "message": "쇼핑을 3개에서 2개로 줄여줘",
        "expected": {"operations": [{"op": "set_quantity", "category": "shopping", "from_quantity": 3, "to_quantity": 2}]},
    },
    {
        "name": "swap_morning_afternoon",
        "message": "2일차 오전이랑 오후 바꿔줘",
        "expected": {"operations": [{"op": "swap", "target_day": 2, "swap_slots": ["morning", "afternoon"]}]},
    },
    {
        "name": "swap_lunch_dinner",
        "message": "3일차 점심이랑 저녁 바꿔줘",
        "expected": {"operations": [{"op": "swap", "target_day": 3, "swap_slots": ["lunch", "dinner"]}]},
    },
    {
        "name": "move_place_morning_to_afternoon",
        "message": "1일차 오전 루브르를 오후로 옮겨줘",
        "expected": {
            "operations": [
                {
                    "op": "move",
                    "target_day": 1,
                    "place_name": "루브르",
                    "target_slot": "afternoon",
                    "constraints_patch": {"from_slot": "morning", "to_slot": "afternoon"},
                }
            ]
        },
    },
    {
        "name": "move_restaurant_lunch_to_dinner",
        "message": "2일차 점심 식당을 저녁으로 옮겨줘",
        "expected": {
            "operations": [
                {
                    "op": "move",
                    "target_day": 2,
                    "category": "restaurant",
                    "target_slot": "dinner",
                    "constraints_patch": {"from_slot": "lunch", "to_slot": "dinner"},
                }
            ]
        },
    },
    {
        "name": "museum_limit_one",
        "message": "미술관 하루 1개만 가도록 바꿔줘",
        "expected": {"operations": [{"op": "set_constraint", "constraints_patch": {"museum_per_day": 1}}]},
    },
    {
        "name": "museum_limit_two",
        "message": "박물관 하루 2개만 가도록 수정해줘",
        "expected": {"operations": [{"op": "set_constraint", "constraints_patch": {"museum_per_day": 2}}]},
    },
    {
        "name": "indoor_constraint",
        "message": "실내 위주로 수정해줘",
        "expected": {"operations": [{"op": "set_constraint", "constraints_patch": {"indoor_focus": True}}]},
    },
    {
        "name": "rainy_and_indoor_constraint",
        "message": "비 오면 실내 위주로 수정해줘",
        "expected": {"operations": [{"op": "set_constraint", "constraints_patch": {"indoor_focus": True, "rainy_plan": True}}]},
    },
    {
        "name": "rainy_constraint_only",
        "message": "비 오면으로 수정해줘",
        "expected": {"operations": [{"op": "set_constraint", "constraints_patch": {"rainy_plan": True}}]},
    },
    {
        "name": "add_night_view_without_day_needs_clarify",
        "message": "야경 명소 하나 더 추가해줘",
        "expected": {"operations": [{"op": "add", "category": "night_view", "quantity": 1}], "clarify": {"needed": True, "missing_fields": ["operations.target_day"]}},
        "context": {"trip_id": "trip-123"},
    },
    {
        "name": "add_cafe_without_day_needs_clarify",
        "message": "카페 하나 더 추가해줘",
        "expected": {"operations": [{"op": "add", "category": "cafe", "quantity": 1}], "clarify": {"needed": True, "missing_fields": ["operations.target_day"]}},
        "context": {"trip_id": "trip-123"},
    },
    {
        "name": "add_cafe_morning",
        "message": "3일차 오전 카페 하나 추가해줘",
        "expected": {"operations": [{"op": "add", "target_day": 3, "target_slot": "morning", "category": "cafe", "quantity": 1}]},
    },
    {
        "name": "add_night_slot",
        "message": "4일차 밤 야경 하나 추가해줘",
        "expected": {"operations": [{"op": "add", "target_day": 4, "target_slot": "night", "category": "night_view", "quantity": 1}]},
    },
    {
        "name": "replace_notredame_to_louvre",
        "message": "노트르담 대신 루브르로 바꿔줘",
        "expected": {"operations": [{"op": "replace", "place_name": "노트르담", "constraints_patch": {"replace_mode": "place_to_place", "to_place": "루브르"}}]},
    },
    {
        "name": "replace_versailles_to_cafe",
        "message": "베르사유 대신 카페 넣어줘",
        "expected": {"operations": [{"op": "replace", "place_name": "베르사유", "category": "cafe", "constraints_patch": {"replace_mode": "place_to_category", "to_category": "cafe"}}]},
    },
    {
        "name": "swap_morning_dinner",
        "message": "1일차 오전이랑 저녁 바꿔줘",
        "expected": {"operations": [{"op": "swap", "target_day": 1, "swap_slots": ["morning", "dinner"]}]},
    },
    {
        "name": "remove_cafe_afternoon",
        "message": "2일차 오후 카페 빼줘",
        "expected": {"operations": [{"op": "remove", "target_day": 2, "target_slot": "afternoon", "category": "cafe"}]},
    },
    {
        "name": "add_restaurant_no_quantity",
        "message": "3일차 점심 맛집 추가해줘",
        "expected": {"operations": [{"op": "add", "target_day": 3, "target_slot": "lunch", "category": "restaurant"}]},
    },
    {
        "name": "set_mobility_transit_and_transfers",
        "message": "대중교통 위주로 환승 적게 바꿔줘",
        "expected": {"operations": [{"op": "set_mobility", "mobility": {"travel_mode": "transit", "optimize": "min_transfers"}}]},
    },
    {
        "name": "set_mobility_limit_and_stroller",
        "message": "하루 7km 이하로, 유모차 가능하게 수정해줘",
        "expected": {"operations": [{"op": "set_mobility", "mobility": {"max_walk_km_per_day": 7, "stroller": True}}]},
    },
    {
        "name": "replace_change_verb",
        "message": "루브르를 오르세로 변경해줘",
        "expected": {"operations": [{"op": "replace", "place_name": "루브르", "constraints_patch": {"replace_mode": "place_to_place", "to_place": "오르세"}}]},
    },
    {
        "name": "missing_trip_id",
        "message": "3일차 카페 하나 추가해줘",
        "expected": {"clarify": {"needed": True, "missing_fields": ["trip_id"]}},
        "context": None,
    },
    {
        "name": "remove_place_exclude_phrase",
        "message": "에펠탑 제외해줘",
        "expected": {"operations": [{"op": "remove", "place_name": "에펠탑"}], "clarify": {"needed": False}},
    },
    {
        "name": "replace_arrow_notation",
        "message": "루브르 -> 오르세로 바꿔줘",
        "expected": {"operations": [{"op": "replace", "place_name": "루브르", "constraints_patch": {"replace_mode": "place_to_place", "to_place": "오르세"}}]},
    },
    {
        "name": "replace_malgo_phrase",
        "message": "루브르 말고 오르세 넣어줘",
        "expected": {"operations": [{"op": "replace", "place_name": "루브르", "constraints_patch": {"replace_mode": "place_to_place", "to_place": "오르세"}}]},
    },
    {
        "name": "set_pace_too_much",
        "message": "일정이 너무 많아 좀 줄여줘",
        "expected": {"operations": [{"op": "set_pace", "pace": "slow"}]},
    },
    {
        "name": "set_pace_more_dense",
        "message": "동선 괜찮으니 더 빡세게 해줘",
        "expected": {"operations": [{"op": "set_pace", "pace": "fast"}]},
    },
    {
        "name": "remove_park_day",
        "message": "5일차 공원 제거해줘",
        "expected": {"operations": [{"op": "remove", "target_day": 5, "category": "park"}]},
    },
    {
        "name": "add_shopping_evening",
        "message": "2일차 저녁 쇼핑 하나 추가해줘",
        "expected": {"operations": [{"op": "add", "target_day": 2, "target_slot": "dinner", "category": "shopping", "quantity": 1}]},
    },
]

MODIFY_CASES.extend(
    [
        {
            "name": "replace_remove_add_phrase",
            "message": "루브르 빼고 오르세 넣어줘",
            "expected": {"operations": [{"op": "replace", "place_name": "루브르", "constraints_patch": {"replace_mode": "place_to_place", "to_place": "오르세"}}]},
        },
        {
            "name": "replace_from_to_phrase",
            "message": "루브르에서 오르세로 바꿔줘",
            "expected": {"operations": [{"op": "replace", "place_name": "루브르", "constraints_patch": {"replace_mode": "place_to_place", "to_place": "오르세"}}]},
        },
        {
            "name": "set_mobility_min_transfers_phrase_variant",
            "message": "환승은 최소로 해줘",
            "expected": {"operations": [{"op": "set_mobility", "mobility": {"optimize": "min_transfers"}}], "clarify": {"needed": False}},
        },
        {
            "name": "set_mobility_subway_mode",
            "message": "지하철 위주로 바꿔줘",
            "expected": {"operations": [{"op": "set_mobility", "mobility": {"travel_mode": "transit"}}], "clarify": {"needed": False}},
        },
        {
            "name": "indoor_constraint_only_phrase",
            "message": "실내로만 수정해줘",
            "expected": {"operations": [{"op": "set_constraint", "constraints_patch": {"indoor_focus": True}}], "clarify": {"needed": False}},
        },
        {
            "name": "set_pace_conflict_prefers_slow",
            "message": "일정이 너무 타이트해서 여유롭게 바꿔줘",
            "expected": {"operations": [{"op": "set_pace", "pace": "slow"}]},
        },
        {
            "name": "set_mobility_reduce_walk_distance",
            "message": "걷는 거리 줄여줘",
            "expected": {"operations": [{"op": "set_mobility", "mobility": {"max_walk_km_per_day": 5, "travel_mode": "transit"}}]},
        },
        {
            "name": "museum_limit_korean_two_words",
            "message": "미술관 하루 두 개만 가도록 바꿔줘",
            "expected": {"operations": [{"op": "set_constraint", "constraints_patch": {"museum_per_day": 2}}]},
        },
        {
            "name": "museum_limit_korean_one_word",
            "message": "박물관 하루 한 개만 가게 바꿔줘",
            "expected": {"operations": [{"op": "set_constraint", "constraints_patch": {"museum_per_day": 1}}]},
        },
        {
            "name": "rainy_and_indoor_uchunsi_phrase",
            "message": "우천 시 실내 위주로 수정해줘",
            "expected": {"operations": [{"op": "set_constraint", "constraints_patch": {"indoor_focus": True, "rainy_plan": True}}]},
        },
        {
            "name": "subway_and_stroller_mobility",
            "message": "지하철 위주로 유모차 가능하게 바꿔줘",
            "expected": {"operations": [{"op": "set_mobility", "mobility": {"travel_mode": "transit", "stroller": True}}]},
        },
        {
            "name": "min_transfers_and_wheelchair_mobility",
            "message": "환승은 최소로 휠체어 가능하게 바꿔줘",
            "expected": {"operations": [{"op": "set_mobility", "mobility": {"optimize": "min_transfers", "wheelchair": True}}]},
        },
        {
            "name": "day_replace_remove_add_phrase",
            "message": "2일차 루브르 빼고 오르세 넣어줘",
            "expected": {"operations": [{"op": "replace", "target_day": 2, "place_name": "루브르", "constraints_patch": {"replace_mode": "place_to_place", "to_place": "오르세"}}]},
        },
        {
            "name": "replace_place_to_category_remove_add",
            "message": "베르사유 빼고 카페 넣어줘",
            "expected": {"operations": [{"op": "replace", "place_name": "베르사유", "category": "cafe", "constraints_patch": {"replace_mode": "place_to_category", "to_category": "cafe"}}]},
        },
        {
            "name": "swap_dinner_and_night",
            "message": "3일차 저녁이랑 밤 바꿔줘",
            "expected": {"operations": [{"op": "swap", "target_day": 3, "swap_slots": ["dinner", "night"]}]},
        },
        {
            "name": "move_cafe_afternoon_to_night",
            "message": "2일차 오후 카페를 밤으로 옮겨줘",
            "expected": {"operations": [{"op": "move", "target_day": 2, "target_slot": "night", "category": "cafe", "constraints_patch": {"from_slot": "afternoon", "to_slot": "night"}}]},
        },
        {
            "name": "add_night_view_without_quantity_day",
            "message": "2일차 밤 야경 추가해줘",
            "expected": {"operations": [{"op": "add", "target_day": 2, "target_slot": "night", "category": "night_view"}]},
        },
        {
            "name": "remove_place_with_day",
            "message": "2일차 루브르 빼줘",
            "expected": {"operations": [{"op": "remove", "target_day": 2, "place_name": "루브르"}]},
        },
        {
            "name": "set_pace_slow_shieom",
            "message": "일정 좀 쉬엄쉬엄하게 바꿔줘",
            "expected": {"operations": [{"op": "set_pace", "pace": "slow"}]},
        },
        {
            "name": "set_pace_fast_dense",
            "message": "일정 좀 빽빽하게 바꿔줘",
            "expected": {"operations": [{"op": "set_pace", "pace": "fast"}]},
        },
        {
            "name": "set_mobility_low_walk_soft_phrase",
            "message": "많이 안 걷게 수정해줘",
            "expected": {"operations": [{"op": "set_mobility", "mobility": {"max_walk_km_per_day": 5, "travel_mode": "transit"}}]},
        },
        {
            "name": "swap_without_day_needs_clarify",
            "message": "오전이랑 밤 바꿔줘",
            "expected": {"operations": [{"op": "swap", "swap_slots": ["morning", "night"]}], "clarify": {"needed": True, "missing_fields": ["operations.target_day"]}},
            "context": {"trip_id": "trip-123"},
        },
        {
            "name": "replace_from_to_change_variant",
            "message": "루브르에서 오르세로 변경해줘",
            "expected": {"operations": [{"op": "replace", "place_name": "루브르", "constraints_patch": {"replace_mode": "place_to_place", "to_place": "오르세"}}]},
        },
        {
            "name": "replace_eiffel_to_cafe_remove_add",
            "message": "에펠탑 빼고 카페 넣어줘",
            "expected": {"operations": [{"op": "replace", "place_name": "에펠탑", "category": "cafe", "constraints_patch": {"replace_mode": "place_to_category", "to_category": "cafe"}}]},
        },
        {
            "name": "set_mobility_bus_mode",
            "message": "버스 위주로 바꿔줘",
            "expected": {"operations": [{"op": "set_mobility", "mobility": {"travel_mode": "transit"}}], "clarify": {"needed": False}},
        },
    ]
)


class ParserRegressionTests(unittest.TestCase):
    maxDiff = None

    def assert_subset(self, expected, actual):
        if isinstance(expected, dict):
            self.assertIsInstance(actual, dict)
            for key, value in expected.items():
                self.assertIn(key, actual)
                self.assert_subset(value, actual[key])
            return

        if isinstance(expected, list):
            self.assertIsInstance(actual, list)
            self.assertGreaterEqual(len(actual), len(expected))
            if all(not isinstance(item, (dict, list)) for item in expected):
                for expected_item in expected:
                    self.assertIn(expected_item, actual)
                return
            for expected_item, actual_item in zip(expected, actual):
                self.assert_subset(expected_item, actual_item)
            return

        self.assertEqual(expected, actual)

    def test_create_jazz_mood_does_not_auto_set_local_theme(self):
        message = "파리 3일 여행인데 비 오는 날에도 괜찮게 실내 위주로 짜고 저녁에는 재즈바 같은 분위기도 있었으면 해."

        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            with redirect_stdout(io.StringIO()):
                payload = parse_create_plan(message).model_dump()

        themes = ((payload.get("preferences") or {}).get("themes") or [])
        travel_style = ((payload.get("preferences") or {}).get("travel_style") or [])

        self.assertIn("nightlife", themes)
        self.assertNotIn("local", themes)
        self.assertIn("nightlife", travel_style)
        self.assertNotIn("local", travel_style)


def _create_test(case):
    def test(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            with redirect_stdout(io.StringIO()):
                payload = parse_create_plan(case["message"]).model_dump()
        self.assert_subset(case["expected"], payload)

    return test


def _modify_test(case):
    def test(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            with redirect_stdout(io.StringIO()):
                payload = parse_modify_plan(case["message"], case.get("context", {"trip_id": "trip-123"})).model_dump()
        self.assert_subset(case["expected"], payload)

    return test


for index, case in enumerate(CREATE_CASES, 1):
    setattr(ParserRegressionTests, f"test_create_{index:03d}_{case['name']}", _create_test(case))


for index, case in enumerate(MODIFY_CASES, 1):
    setattr(ParserRegressionTests, f"test_modify_{index:03d}_{case['name']}", _modify_test(case))


if __name__ == "__main__":
    unittest.main()
