import unittest

from app.services.planning_brief_service import build_planning_brief, validate_planning_brief_compliance
from parser_api.services.place_catalog import build_itinerary


def _real_titles(itinerary_days: list[dict]) -> list[str]:
    return [
        str((item.get("place") or {}).get("name") or item.get("title") or "")
        for day in itinerary_days
        for item in day.get("items") or []
        if item.get("itemKind") != "gap"
    ]


class PlanningBriefComplianceTests(unittest.TestCase):
    def test_validate_planning_brief_allows_six_stop_slow_romantic_landmark_day(self) -> None:
        planning_brief = {
            "pace": "slow",
            "travel_style": ["romance", "landmark", "classic", "couple"],
        }
        itinerary_days = [
            {
                "day_number": 1,
                "items": [
                    {
                        "time_slot": "morning",
                        "start_time": "09:30",
                        "title": "Louvre Museum",
                        "role": "museum_or_gallery",
                        "place": {"name": "Louvre Museum", "category": "museum", "role": "museum_or_gallery"},
                        "duration_minutes": 120,
                    },
                    {
                        "time_slot": "afternoon",
                        "start_time": "11:45",
                        "title": "Seine River Walk",
                        "role": "walking_route",
                        "place": {"name": "Seine River Walk", "category": "neighborhood", "role": "walking_route"},
                        "duration_minutes": 60,
                    },
                    {
                        "time_slot": "afternoon",
                        "start_time": "13:00",
                        "title": "Saint-Germain Cafe",
                        "role": "cafe_break",
                        "place": {"name": "Saint-Germain Cafe", "category": "cafe", "role": "cafe_break"},
                        "duration_minutes": 45,
                    },
                    {
                        "time_slot": "evening",
                        "start_time": "18:15",
                        "title": "La Robe et le Palais",
                        "role": "dinner",
                        "place": {"name": "La Robe et le Palais", "category": "restaurant", "role": "dinner", "cuisine": ["French"]},
                        "duration_minutes": 90,
                    },
                    {
                        "time_slot": "evening",
                        "start_time": "20:00",
                        "title": "Eiffel Tower",
                        "role": "landmark",
                        "place": {"name": "Eiffel Tower", "category": "landmark", "role": "landmark"},
                        "duration_minutes": 60,
                    },
                    {
                        "time_slot": "night",
                        "start_time": "21:20",
                        "title": "Arc de Triomphe",
                        "role": "landmark",
                        "place": {"name": "Arc de Triomphe", "category": "landmark", "role": "landmark"},
                        "duration_minutes": 50,
                    },
                ],
            }
        ]

        validation = validate_planning_brief_compliance(itinerary_days, planning_brief)

        self.assertFalse(validation["pace_violations"])

    def test_validate_planning_brief_allows_six_stop_slow_day_with_recovery_beats(self) -> None:
        planning_brief = {
            "pace": "slow",
            "travel_style": ["indoor", "cafe"],
        }
        itinerary_days = [
            {
                "day_number": 1,
                "items": [
                    {
                        "time_slot": "morning",
                        "start_time": "09:45",
                        "title": "Cafe Start",
                        "role": "cafe_break",
                        "place": {"name": "Cafe Start", "category": "cafe", "role": "cafe_break"},
                        "duration_minutes": 45,
                    },
                    {
                        "time_slot": "morning",
                        "start_time": "10:45",
                        "title": "Musee d'Orsay",
                        "role": "museum_or_gallery",
                        "place": {"name": "Musee d'Orsay", "category": "museum", "role": "museum_or_gallery"},
                        "duration_minutes": 120,
                    },
                    {
                        "time_slot": "lunch",
                        "start_time": "12:45",
                        "title": "Lunch",
                        "role": "lunch",
                        "place": {"name": "Lunch", "category": "restaurant", "role": "lunch"},
                        "duration_minutes": 75,
                    },
                    {
                        "time_slot": "afternoon",
                        "start_time": "14:30",
                        "title": "Seine Walk",
                        "role": "walking_route",
                        "place": {"name": "Seine Walk", "category": "neighborhood", "role": "walking_route"},
                        "duration_minutes": 50,
                    },
                    {
                        "time_slot": "afternoon",
                        "start_time": "16:00",
                        "title": "Afternoon Cafe",
                        "role": "cafe_break",
                        "place": {"name": "Afternoon Cafe", "category": "cafe", "role": "cafe_break"},
                        "duration_minutes": 45,
                    },
                    {
                        "time_slot": "evening",
                        "start_time": "18:30",
                        "title": "Dinner",
                        "role": "dinner",
                        "place": {"name": "Dinner", "category": "restaurant", "role": "dinner"},
                        "duration_minutes": 90,
                    },
                ],
            }
        ]

        validation = validate_planning_brief_compliance(itinerary_days, planning_brief)

        self.assertFalse(validation["pace_violations"])

    def test_arc_constraint_does_not_match_unrelated_marche_landmark(self) -> None:
        planning_brief = {"must_include": ["개선문"]}
        itinerary_days = [
            {
                "day_number": 1,
                "items": [
                    {
                        "time_slot": "afternoon",
                        "title": "Marché aux Timbres",
                        "place": {"name": "Marché aux Timbres", "category": "landmark", "slug": "osm-marcheauxtimbres-1512"},
                        "duration_minutes": 45,
                    }
                ],
            }
        ]

        validation = validate_planning_brief_compliance(itinerary_days, planning_brief)

        self.assertEqual(validation["missing_must_include"], ["개선문"])

    def test_build_planning_brief_extracts_final_anchor_from_repeated_place_mentions(self) -> None:
        message = "기념일 여행이라 에펠탑 야경은 꼭 넣어줘. 마지막은 에펠탑으로 끝내줘."

        planning_brief = build_planning_brief(plan={"_source_message": message}, intent="create_trip")

        self.assertEqual(planning_brief.get("final_anchor"), "에펠탑")

    def test_build_planning_brief_treats_seine_walk_as_final_anchor(self) -> None:
        message = "저녁 먹고 센강 산책으로 마무리하고 싶어."

        planning_brief = build_planning_brief(plan={"_source_message": message}, intent="create_trip")

        self.assertEqual(planning_brief.get("final_anchor"), "센강 산책")

    def test_build_planning_brief_marks_morning_slot_for_early_start_request(self) -> None:
        message = "아침 일찍 시작해서 밤부터 시작하지 말고 오전부터 파리 관광지 위주로 돌고 싶어."

        planning_brief = build_planning_brief(plan={"_source_message": message}, intent="create_trip")

        self.assertIn("morning", planning_brief.get("preferred_time_slots") or [])
        self.assertEqual(planning_brief.get("start_time"), "09:00")

    def test_build_planning_brief_marks_bar_mood_and_indoor_rain_signals(self) -> None:
        message = "비 오는 날이라 실내 위주로 보고 싶고 밤에는 바 분위기나 칵테일 한잔할 만한 곳도 있으면 좋겠어."

        planning_brief = build_planning_brief(plan={"_source_message": message}, intent="create_trip")

        self.assertIn("indoor", planning_brief.get("travel_style") or [])
        self.assertIn("nightlife", planning_brief.get("travel_style") or [])
        self.assertIn("bar", planning_brief.get("meal_preference") or [])

    def test_jazz_mood_does_not_auto_add_local_style(self) -> None:
        message = "비 오는 날에도 괜찮게 실내 위주로 짜고 저녁에는 재즈바 같은 분위기도 있었으면 해."

        planning_brief = build_planning_brief(plan={"_source_message": message}, intent="create_trip")

        self.assertIn("jazz", planning_brief.get("travel_style") or [])
        self.assertIn("nightlife", planning_brief.get("travel_style") or [])
        self.assertIn("indoor", planning_brief.get("travel_style") or [])
        self.assertNotIn("local", planning_brief.get("travel_style") or [])
        self.assertIn("jazz_bar", planning_brief.get("meal_preference") or [])

    def test_self_correction_addendum_does_not_pollute_user_intent(self) -> None:
        message = (
            "비 오는 날에도 괜찮게 실내 위주로 짜고 저녁에는 재즈바 같은 분위기도 있었으면 해.\n\n"
            "[Planner self-correction context]\n"
            "Repair suggestions:\n"
            "- Replace one or more iconic-heavy stops with a neighborhood, park, cafe, or quieter local block."
        )

        planning_brief = build_planning_brief(plan={"_source_message": message}, intent="create_trip")

        self.assertIn("jazz", planning_brief.get("travel_style") or [])
        self.assertIn("indoor", planning_brief.get("travel_style") or [])
        self.assertNotIn("local", planning_brief.get("travel_style") or [])

    def test_build_planning_brief_captures_low_walking_vegetarian_cathedral_avoid_and_saint_germain(self) -> None:
        message = "많이 걷는 건 싫고 채식 위주로 먹고 싶어. 성당이나 종교 건축물은 빼고 생제르맹이랑 마레 위주로 부탁해."

        planning_brief = build_planning_brief(plan={"_source_message": message}, intent="create_trip")
        itinerary = build_itinerary({"dates": {"days": 1}, "planning_brief": planning_brief})
        titles = _real_titles(itinerary["itinerary_days"])

        self.assertEqual(planning_brief["pace"], "slow")
        self.assertEqual(planning_brief["transport_preference"], "transit")
        self.assertIn("vegetarian", planning_brief["meal_preference"])
        self.assertTrue(any("생제르맹" in value for value in planning_brief["must_include"]))
        self.assertIn("노트르담 대성당", planning_brief["must_avoid"])
        self.assertIn("생트샤펠", planning_brief["must_avoid"])
        self.assertTrue(any("saint-germain" in title.lower() for title in titles))

    def test_landmark_minimize_signal_does_not_auto_include_classic_landmarks(self) -> None:
        message = "유명한 랜드마크는 최소화하고 마레랑 생제르맹 같은 동네 위주로 천천히 걷고 싶어."

        planning_brief = build_planning_brief(plan={"_source_message": message}, intent="create_trip")

        self.assertFalse(any(value in {"에펠탑", "루브르 박물관", "개선문"} for value in planning_brief["must_include"]))
        self.assertTrue(any("마레" in value for value in planning_brief["must_include"]))
        self.assertTrue(any("생제르맹" in value for value in planning_brief["must_include"]))

    def test_nightlife_avoid_signal_does_not_add_jazz_bar(self) -> None:
        message = "아이랑 같이 가니까 재즈바 같은 밤 장소는 빼고 공원 하나랑 디저트는 꼭 넣어줘."

        planning_brief = build_planning_brief(plan={"_source_message": message}, intent="create_trip")

        self.assertFalse(any("위셰트" in value or "재즈" in value for value in planning_brief["must_include"]))
        self.assertIn("르 카보 드 라 위셰트", planning_brief["must_avoid"])
        self.assertFalse(any(value in {"jazz", "jazz_bar", "bar", "wine"} for value in planning_brief["meal_preference"]))

    def test_museum_deprioritize_signal_does_not_auto_include_orsay(self) -> None:
        message = "개선문 야경은 꼭 보고 싶지만 낮에는 박물관보다 공원과 카페가 좋아."

        planning_brief = build_planning_brief(plan={"_source_message": message}, intent="create_trip")

        self.assertNotIn("오르세 미술관", planning_brief["must_include"])
        self.assertFalse(any(value in {"museum", "art", "culture"} for value in planning_brief["travel_style"]))

    def test_late_start_brunch_request_does_not_auto_expand_into_morning_cafe_style(self) -> None:
        message = "늦게 시작하는 파리 3일 여행 짜줘. 브런치 먹고 오후부터 천천히 돌아다니고 싶어."

        planning_brief = build_planning_brief(plan={"_source_message": message}, intent="create_trip")

        self.assertIn("brunch", planning_brief["meal_preference"])
        self.assertNotIn("cafe", planning_brief["travel_style"])
        self.assertIn("afternoon", planning_brief["preferred_time_slots"])
        self.assertIn("lunch", planning_brief["preferred_time_slots"])
        self.assertNotIn("morning", planning_brief["preferred_time_slots"])
        self.assertEqual(planning_brief.get("start_time"), "12:00")

    def test_mixed_include_and_avoid_sentence_keeps_louvre_in_must_avoid(self) -> None:
        message = "에펠탑 야경은 꼭 보고 싶고 루브르는 빼고 싶어. 디저트랑 산책 위주로 여유롭게 짜줘."

        planning_brief = build_planning_brief(plan={"_source_message": message}, intent="create_trip")

        self.assertIn("에펠탑", planning_brief["must_include"])
        self.assertIn("루브르 박물관", planning_brief["must_avoid"])
        self.assertNotIn("루브르 박물관", planning_brief["must_include"])

    def test_spaced_packed_phrase_is_recognized_as_fast_pace(self) -> None:
        message = "쇼핑이랑 랜드마크 둘 다 챙기고 싶은 파리 2박3일 일정 짜줘. 꽉 차게."

        planning_brief = build_planning_brief(plan={"_source_message": message}, intent="create_trip")

        self.assertEqual(planning_brief.get("pace"), "fast")

    def test_validate_planning_brief_compliance_does_not_treat_louvre_restaurant_as_louvre_museum(self) -> None:
        planning_brief = {"must_avoid": ["루브르 박물관"]}
        itinerary_days = [
            {
                "day_number": 1,
                "items": [
                    {
                        "time_slot": "lunch",
                        "title": "Brasserie du Louvre",
                        "place": {"name": "Brasserie du Louvre", "category": "restaurant", "slug": "brasserie-du-louvre"},
                        "duration_minutes": 90,
                    }
                ],
            }
        ]

        validation = validate_planning_brief_compliance(itinerary_days, planning_brief)

        self.assertFalse(validation["included_must_avoid"])

    def test_brief_driven_itinerary_respects_primary_user_constraints(self) -> None:
        message = (
            "파리 2박 3일 일정 짜줘. 에펠탑 야경은 꼭 보고 싶고, 루브르는 가지 않을래. "
            "하루에 너무 많이 돌아다니는 건 싫고, 카페랑 디저트 위주로 여유롭게 다니고 싶어. "
            "저녁은 분위기 좋은 프렌치 레스토랑으로 추천해줘."
        )
        parsed = {
            "_source_message": message,
            "dates": {"days": 3},
            "preferences": {},
            "mobility": {},
            "budget": {},
            "pace": {},
        }

        planning_brief = build_planning_brief(plan=parsed, intent="create_trip")
        itinerary = build_itinerary({**parsed, "planning_brief": planning_brief})
        itinerary_days = itinerary["itinerary_days"]
        validation = validate_planning_brief_compliance(itinerary_days, planning_brief)
        titles = _real_titles(itinerary_days)

        self.assertEqual(planning_brief["pace"], "slow")
        self.assertTrue(planning_brief["night_view_required"])
        self.assertTrue(planning_brief["locked_stops"])
        self.assertIn(planning_brief["preferred_blueprints"][0], {"slow_cafe_evening_day", "night_view_focused_day"})
        self.assertTrue(any("에펠" in title or "eiffel" in title.lower() for title in titles))
        self.assertTrue(all("루브르" not in title and "louvre" not in title.lower() for title in titles))
        self.assertTrue(any(item.get("isNightViewSpot") for day in itinerary_days for item in day.get("items") or []))
        self.assertFalse(validation["missing_must_include"])
        self.assertFalse(validation["included_must_avoid"])
        self.assertFalse(validation["time_slot_violations"])
        self.assertFalse(validation["pace_violations"])
        self.assertGreaterEqual(float(validation["final_quality_score"]), 0.75)

    def test_alias_matching_accepts_english_place_name_for_korean_constraints(self) -> None:
        planning_brief = {
            "must_include": ["에펠탑"],
            "must_avoid": ["루브르 박물관"],
        }
        itinerary_days = [
            {
                "day_number": 1,
                "items": [
                    {
                        "time_slot": "evening",
                        "title": "Eiffel Tower",
                        "place": {"name": "Eiffel Tower", "category": "landmark"},
                        "duration_minutes": 90,
                    }
                ],
            }
        ]

        validation = validate_planning_brief_compliance(itinerary_days, planning_brief)

        self.assertFalse(validation["missing_must_include"])
        self.assertFalse(validation["included_must_avoid"])

    def test_long_helper_blocks_trigger_quality_replan_even_if_item_kind_is_stop(self) -> None:
        planning_brief = {
            "pace": "slow",
            "must_include": ["에펠탑"],
        }
        itinerary_days = [
            {
                "day_number": 1,
                "items": [
                    {
                        "time_slot": "evening",
                        "title": "Eiffel Tower",
                        "place": {"name": "Eiffel Tower", "category": "landmark"},
                        "duration_minutes": 90,
                    },
                    {
                        "time_slot": "afternoon",
                        "title": "점심 전 자유 시간",
                        "itemKind": "stop",
                        "place": {"name": "점심 전 자유 시간", "category": "free_time"},
                        "duration_minutes": 100,
                    },
                    {
                        "time_slot": "evening",
                        "title": "저녁 전 재정비와 카페 휴식",
                        "itemKind": "stop",
                        "place": {"name": "저녁 전 재정비와 카페 휴식", "category": "free_time"},
                        "duration_minutes": 70,
                    },
                ],
            }
        ]

        validation = validate_planning_brief_compliance(itinerary_days, planning_brief)

        self.assertIn("story_flow", validation["violated_constraints"])
        self.assertTrue(validation["quality_violations"])
        self.assertTrue(validation["needs_replan"])


if __name__ == "__main__":
    unittest.main()
