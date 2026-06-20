import unittest

from app.services.daily_quality_validator_service import evaluate_itinerary_quality
from app.services.plan_evaluator_service import evaluate_plan
from app.services.planning_brief_service import build_planning_brief
from parser_api.services.place_catalog import build_itinerary


def _item(
    *,
    title: str,
    category: str,
    role: str,
    start_time: str,
    lat: float,
    lng: float,
    description: str = "",
) -> dict:
    return {
        "id": f"item-{title}-{start_time}",
        "time_slot": "lunch" if role == "lunch" else "evening" if role in {"dinner", "night_activity"} else "afternoon",
        "start_time": start_time,
        "role": role,
        "title": title,
        "place": {
            "place_id": title.lower().replace(" ", "-"),
            "name": title,
            "category": category,
            "role": role,
            "coordinates": {"lat": lat, "lng": lng},
            "is_main_activity": role in {"main_activity", "museum_or_gallery", "landmark", "shopping"},
            "is_meal": role in {"lunch", "dinner"},
            "is_cafe": role in {"cafe_break", "dessert"} or category in {"cafe", "bakery"},
            "is_art_or_culture": role == "museum_or_gallery" or category in {"museum", "gallery"},
        },
        "isMeal": role in {"lunch", "dinner"},
        "description": description or f"{title} fits the day theme.",
    }


def _day(day_number: int, theme: str, items: list[dict]) -> dict:
    return {
        "day_number": day_number,
        "dayTheme": theme,
        "theme": theme,
        "title": theme,
        "items": items,
    }


class PlanEvaluatorQualityTests(unittest.TestCase):
    def test_romantic_night_view_prompt_generated_itinerary_passes_quality(self) -> None:
        message = "커플 파리 4일 여행인데 로맨틱하고 여유롭게 짜주고 저녁 야경은 꼭 살려줘."
        parsed = {
            "_source_message": message,
            "dates": {"start_date": "2026-07-01", "days": 4},
            "preferences": {},
            "mobility": {},
            "budget": {},
            "pace": {},
        }
        brief = build_planning_brief(plan=parsed, intent="create_trip", language="ko")
        trip = build_itinerary({**parsed, "planning_brief": brief})

        evaluation = evaluate_itinerary_quality(trip["itinerary_days"], brief, prompt=message, language="ko")

        self.assertTrue(evaluation["passed"])
        self.assertTrue(all(day["passed"] for day in evaluation["days"]))

    def test_late_start_brunch_prompt_generated_itinerary_passes_quality(self) -> None:
        message = "늦게 시작하는 파리 3일 여행 짜줘. 브런치 먹고 오후부터 천천히 돌아다니고 싶어."
        parsed = {
            "_source_message": message,
            "dates": {"start_date": "2026-07-01", "days": 3},
            "preferences": {},
            "mobility": {},
            "budget": {},
            "pace": {},
        }
        brief = build_planning_brief(plan=parsed, intent="create_trip", language="ko")
        trip = build_itinerary({**parsed, "planning_brief": brief})

        evaluation = evaluate_itinerary_quality(trip["itinerary_days"], brief, prompt=message, language="ko")
        first_day = trip["itinerary_days"][0]
        first_real_item = next(item for item in first_day["items"] if item.get("itemKind") != "gap")

        self.assertTrue(evaluation["passed"])
        self.assertGreaterEqual(first_real_item["start_time"], "10:30")
        self.assertTrue(all(day["passed"] for day in evaluation["days"]))

    def test_art_trip_generated_itinerary_keeps_daily_quality_constraints(self) -> None:
        message = "파리 5일 미술관 여행. 맛집, 랜드마크, 쇼핑, 카페도 포함해줘."
        parsed = {
            "_source_message": message,
            "dates": {"start_date": "2026-07-01", "days": 5},
            "preferences": {},
            "mobility": {},
            "budget": {},
            "pace": {},
        }
        brief = build_planning_brief(plan=parsed, intent="create_trip", language="ko")
        parsed["planning_brief"] = brief
        trip = build_itinerary(parsed)

        evaluation = evaluate_plan(trip["itinerary_days"], brief, prompt=message, language="ko")
        daily = evaluation["daily_quality"]

        self.assertEqual(len(daily), 5)
        self.assertTrue(all(day["quality_checks"]["max_cafes_ok"] for day in daily))
        self.assertTrue(all(day["quality_checks"]["main_activity_exists"] for day in daily))
        self.assertTrue(all(day["quality_checks"]["art_day_ok"] for day in daily))
        self.assertTrue(all(day["quality_checks"]["category_diversity_ok"] for day in daily))
        self.assertTrue(all(day["quality_checks"]["meal_timing_ok"] for day in daily))

    def test_cafe_six_day_is_rejected(self) -> None:
        itinerary_days = [
            _day(
                1,
                "Marais cafe hopping day",
                [
                    _item(title=f"Cafe {index}", category="cafe", role="cafe_break", start_time=f"{9 + index:02d}:00", lat=48.85 + index * 0.001, lng=2.35 + index * 0.001, description="Relaxing atmosphere and slow pace.")
                    for index in range(6)
                ],
            )
        ]
        brief = {"travel_style": ["cafe", "foodie"], "source_text": "카페 위주 하루"}

        evaluation = evaluate_plan(itinerary_days, brief, prompt="카페 많은 하루", language="ko")
        issues = evaluation["itinerary_quality"]["days"][0]["errors"]

        self.assertFalse(evaluation["itinerary_quality"]["days"][0]["passed"])
        self.assertTrue(any("cap cafe breaks" in issue for issue in issues))

    def test_two_consecutive_cafes_are_flagged(self) -> None:
        itinerary_days = [
            _day(
                1,
                "Cafe before museum",
                [
                    _item(title="Morning Cafe", category="cafe", role="cafe_break", start_time="09:30", lat=48.8500, lng=2.3500),
                    _item(title="Bakery Stop", category="bakery", role="cafe_break", start_time="10:20", lat=48.8510, lng=2.3510),
                    _item(title="Musee d'Orsay", category="museum", role="museum_or_gallery", start_time="11:30", lat=48.8600, lng=2.3266),
                    _item(title="Lunch", category="restaurant", role="lunch", start_time="13:10", lat=48.8610, lng=2.3290),
                    _item(title="Dinner", category="restaurant", role="dinner", start_time="19:00", lat=48.8578, lng=2.3522),
                ],
            )
        ]
        brief = {"travel_style": ["cafe", "foodie"], "source_text": "카페 위주 여행"}

        evaluation = evaluate_plan(itinerary_days, brief, prompt="카페 위주 여행", language="ko")
        issues = evaluation["itinerary_quality"]["days"][0]["errors"]

        self.assertTrue(any("back-to-back" in issue for issue in issues))

    def test_late_lunch_is_flagged(self) -> None:
        itinerary_days = [
            _day(
                1,
                "Left Bank museum and dinner day",
                [
                    _item(title="Musee d'Orsay", category="museum", role="museum_or_gallery", start_time="10:00", lat=48.8600, lng=2.3266),
                    _item(title="Late Lunch Bistro", category="restaurant", role="lunch", start_time="15:30", lat=48.8610, lng=2.3290),
                    _item(title="Seine Walk", category="neighborhood", role="walking_route", start_time="17:00", lat=48.8588, lng=2.3470),
                    _item(title="Dinner", category="restaurant", role="dinner", start_time="19:30", lat=48.8578, lng=2.3522),
                ],
            )
        ]
        brief = {"travel_style": ["museum", "art"], "source_text": "미술관 여행"}

        evaluation = evaluate_plan(itinerary_days, brief, prompt="미술관 여행", language="ko")
        issues = evaluation["itinerary_quality"]["days"][0]["errors"]

        self.assertTrue(any("Lunch is scheduled at 15:30" in issue for issue in issues))

    def test_raw_early_start_request_flags_evening_first_stop(self) -> None:
        itinerary_days = [
            _day(
                1,
                "Night-first draft",
                [
                    {
                        "id": "night-start",
                        "time_slot": "evening",
                        "start_time": "19:30",
                        "role": "night_activity",
                        "title": "Seine River Walk",
                        "place": {
                            "place_id": "seine-river-walk",
                            "name": "Seine River Walk",
                            "category": "landmark",
                            "role": "night_activity",
                            "coordinates": {"lat": 48.8588, "lng": 2.3470},
                        },
                        "description": "Night river walk.",
                    },
                    _item(title="Dinner", category="restaurant", role="dinner", start_time="21:00", lat=48.8578, lng=2.3522),
                ],
            )
        ]
        brief = {"source_text": "아침 일찍 시작해서 밤부터 시작하지 말고 오전부터 돌고 싶어."}

        evaluation = evaluate_plan(itinerary_days, brief, prompt=brief["source_text"], language="ko")

        self.assertTrue(any(failure.get("target") == "early_start" for failure in evaluation["failures"]))

    def test_museum_trip_without_art_is_rejected(self) -> None:
        itinerary_days = [
            _day(
                1,
                "Classic Paris walk and dinner",
                [
                    _item(title="Arc de Triomphe", category="landmark", role="landmark", start_time="10:00", lat=48.8738, lng=2.2950),
                    _item(title="Lunch", category="restaurant", role="lunch", start_time="12:30", lat=48.8690, lng=2.3070),
                    _item(title="Champs Elysees", category="shopping", role="shopping", start_time="14:30", lat=48.8698, lng=2.3078),
                    _item(title="Dinner", category="restaurant", role="dinner", start_time="19:15", lat=48.8660, lng=2.3200),
                ],
            )
        ]
        brief = {"travel_style": ["museum", "art"], "source_text": "museum trip"}

        evaluation = evaluate_plan(itinerary_days, brief, prompt="museum trip", language="en")
        issues = evaluation["itinerary_quality"]["days"][0]["errors"]

        self.assertFalse(evaluation["passed"])
        self.assertTrue(any("without an art/culture stop" in issue for issue in issues))

    def test_multiday_art_trip_with_only_one_museum_triggers_concept_mismatch(self) -> None:
        itinerary_days = [
            _day(
                1,
                "Museum opener",
                [
                    _item(title="Louvre Museum", category="museum", role="museum_or_gallery", start_time="10:00", lat=48.8606, lng=2.3376),
                    _item(title="Lunch", category="restaurant", role="lunch", start_time="12:30", lat=48.8610, lng=2.3380),
                    _item(title="Dinner", category="restaurant", role="dinner", start_time="19:00", lat=48.8578, lng=2.3522),
                ],
            ),
            _day(
                2,
                "Night view day",
                [
                    _item(title="Luxembourg Gardens", category="park", role="walking_route", start_time="10:30", lat=48.8462, lng=2.3372),
                    _item(title="Lunch 2", category="restaurant", role="lunch", start_time="12:40", lat=48.8468, lng=2.3380),
                    _item(title="Eiffel Tower", category="landmark", role="landmark", start_time="20:00", lat=48.8584, lng=2.2945),
                ],
            ),
            _day(
                3,
                "Neighborhood day",
                [
                    _item(title="Marais Walk", category="neighborhood", role="walking_route", start_time="11:00", lat=48.8575, lng=2.3580),
                    _item(title="Lunch 3", category="restaurant", role="lunch", start_time="12:50", lat=48.8580, lng=2.3585),
                    _item(title="Dinner 3", category="restaurant", role="dinner", start_time="19:00", lat=48.8578, lng=2.3522),
                ],
            ),
        ]
        brief = {"travel_style": ["museum", "art", "night_view"], "source_text": "미술관이랑 야경 중심"}

        evaluation = evaluate_plan(itinerary_days, brief, prompt="미술관이랑 야경 중심", language="ko")

        self.assertTrue(any(failure["type"] == "concept_mismatch" for failure in evaluation["failures"]))

    def test_heavy_night_tail_is_rejected(self) -> None:
        itinerary_days = [
            _day(
                1,
                "Late shopping push",
                [
                    _item(title="Breakfast Walk", category="neighborhood", role="walking_route", start_time="09:30", lat=48.8530, lng=2.3499),
                    _item(title="Louvre Museum", category="museum", role="museum_or_gallery", start_time="10:30", lat=48.8606, lng=2.3376),
                    _item(title="Lunch", category="restaurant", role="lunch", start_time="12:45", lat=48.8600, lng=2.3360),
                    _item(title="Galeries Lafayette", category="shopping", role="shopping", start_time="20:30", lat=48.8720, lng=2.3320),
                ],
            )
        ]
        brief = {"travel_style": ["shopping"], "source_text": "쇼핑 위주 일정"}

        evaluation = evaluate_plan(itinerary_days, brief, prompt="쇼핑 위주 일정", language="ko")
        issues = evaluation["itinerary_quality"]["days"][0]["errors"]

        self.assertTrue(any("softer evening close" in issue for issue in issues))

    def test_repetitive_category_run_is_rejected(self) -> None:
        itinerary_days = [
            _day(
                1,
                "Historic center walk",
                [
                    _item(title="Notre-Dame", category="landmark", role="landmark", start_time="09:30", lat=48.8530, lng=2.3499),
                    _item(title="Sainte-Chapelle", category="landmark", role="landmark", start_time="11:00", lat=48.8554, lng=2.3450),
                    _item(title="Louvre Pyramid", category="landmark", role="landmark", start_time="12:15", lat=48.8610, lng=2.3358),
                    _item(title="Lunch", category="restaurant", role="lunch", start_time="13:00", lat=48.8600, lng=2.3360),
                    _item(title="Tuileries Garden", category="park", role="walking_route", start_time="15:00", lat=48.8635, lng=2.3273),
                    _item(title="Dinner", category="restaurant", role="dinner", start_time="19:00", lat=48.8620, lng=2.3300),
                ],
            )
        ]
        brief = {"travel_style": ["landmark"], "source_text": "랜드마크 위주"}

        evaluation = evaluate_plan(itinerary_days, brief, prompt="랜드마크 위주 일정", language="ko")
        issues = evaluation["itinerary_quality"]["days"][0]["errors"]

        self.assertTrue(any("same category repeats more than twice" in issue.lower() for issue in issues))

    def test_shopping_foodie_request_without_shopping_triggers_concept_mismatch(self) -> None:
        itinerary_days = [
            _day(
                1,
                "Cafe and dinner day",
                [
                    _item(title="Morning Cafe", category="cafe", role="cafe_break", start_time="10:00", lat=48.8500, lng=2.3500),
                    _item(title="Left Bank Walk", category="neighborhood", role="walking_route", start_time="11:30", lat=48.8510, lng=2.3510),
                    _item(title="Lunch Bistro", category="restaurant", role="lunch", start_time="13:00", lat=48.8520, lng=2.3520),
                    _item(title="Seine Walk", category="neighborhood", role="walking_route", start_time="16:00", lat=48.8530, lng=2.3530),
                    _item(title="Dinner", category="restaurant", role="dinner", start_time="19:00", lat=48.8540, lng=2.3540),
                ],
            )
        ]
        brief = {"travel_style": ["shopping", "foodie"], "meal_preference": ["french"], "source_text": "쇼핑이랑 맛집 위주"}

        evaluation = evaluate_plan(itinerary_days, brief, prompt="쇼핑이랑 맛집 위주", language="ko")

        self.assertTrue(any(failure["type"] == "concept_mismatch" for failure in evaluation["failures"]))

    def test_romantic_request_without_evening_mood_triggers_concept_mismatch(self) -> None:
        itinerary_days = [
            _day(
                1,
                "Museum and shopping day",
                [
                    _item(title="Louvre Museum", category="museum", role="museum_or_gallery", start_time="09:30", lat=48.8606, lng=2.3376),
                    _item(title="Lunch", category="restaurant", role="lunch", start_time="12:40", lat=48.8610, lng=2.3380),
                    _item(title="Galeries Lafayette", category="shopping", role="shopping", start_time="14:30", lat=48.8720, lng=2.3320),
                    _item(title="Tuileries Garden", category="park", role="walking_route", start_time="16:30", lat=48.8635, lng=2.3273),
                ],
            )
        ]
        brief = {"travel_style": ["romance", "landmark"], "source_text": "로맨틱한 여행"}

        evaluation = evaluate_plan(itinerary_days, brief, prompt="로맨틱한 여행", language="ko")

        self.assertTrue(any(failure["type"] == "concept_mismatch" for failure in evaluation["failures"]))

    def test_locked_stop_without_coordinates_is_reported_as_resolution_failure(self) -> None:
        itinerary_days = [
            _day(
                1,
                "Eiffel night",
                [
                    {
                        "id": "item-eiffel-night",
                        "time_slot": "evening",
                        "start_time": "19:30",
                        "role": "landmark",
                        "title": "Eiffel Tower",
                        "place": {
                            "place_id": "eiffel-tower",
                            "slug": "eiffel-tower",
                            "name": "Eiffel Tower",
                            "category": "landmark",
                            "coordinates": None,
                        },
                        "resolutionStatus": "unresolved",
                        "description": "Night-view anchor without coordinates.",
                    }
                ],
            )
        ]
        brief = {
            "locked_stops": [{"slug": "eiffel-tower", "target_slot": "evening", "label": "에펠탑 야경"}],
            "source_text": "에펠탑 야경은 꼭 넣어줘",
        }

        evaluation = evaluate_plan(itinerary_days, brief, prompt="에펠탑 야경은 꼭 넣어줘", language="ko")
        hard_types = {failure["failure_type"] for failure in evaluation["hard_failures"]}

        self.assertIn("PLACE_RESOLUTION_FAILED", hard_types)

    def test_final_anchor_matching_accepts_saint_germain_alias(self) -> None:
        itinerary_days = [
            _day(
                1,
                "Left Bank local walk",
                [
                    _item(title="Marais Walk", category="neighborhood", role="walking_route", start_time="14:00", lat=48.8578, lng=2.3622),
                    _item(title="Saint-Germain-des-Pres", category="neighborhood", role="walking_route", start_time="19:30", lat=48.8538, lng=2.3336),
                ],
            )
        ]
        brief = {"final_anchor": "생제르맹 데 프레", "source_text": "마지막은 생제르맹으로 끝내줘"}

        evaluation = evaluate_plan(itinerary_days, brief, prompt="마지막은 생제르맹으로 끝내줘", language="ko")

        self.assertFalse(any(failure["type"] == "final_anchor_mismatch" for failure in evaluation["failures"]))

    def test_museum_limit_ignores_restaurant_named_after_museum(self) -> None:
        itinerary_days = [
            _day(
                1,
                "Indoor art day",
                [
                    _item(title="Musee d'Orsay", category="museum", role="museum_or_gallery", start_time="10:00", lat=48.8600, lng=2.3266),
                    _item(title="Restaurant du Musée d'Orsay", category="restaurant", role="lunch", start_time="12:30", lat=48.8605, lng=2.3270),
                    _item(title="Saint-Germain-des-Pres", category="neighborhood", role="walking_route", start_time="15:00", lat=48.8538, lng=2.3336),
                    _item(title="Dinner", category="restaurant", role="dinner", start_time="19:00", lat=48.8578, lng=2.3522),
                ],
            )
        ]
        brief = {"source_text": "박물관은 하루에 한 곳만", "museum_limit_per_day": 1}

        evaluation = evaluate_plan(itinerary_days, brief, prompt="박물관은 하루에 한 곳만", language="ko")

        self.assertFalse(any(failure["type"] == "museum_limit_violation" for failure in evaluation["failures"]))

    def test_raw_avoid_does_not_flip_prior_required_anchor_when_later_subject_changes(self) -> None:
        itinerary_days = [
            _day(
                1,
                "Low walking museum day",
                [
                    _item(title="Musee d'Orsay", category="museum", role="museum_or_gallery", start_time="10:00", lat=48.8600, lng=2.3266),
                    _item(title="Lunch", category="restaurant", role="lunch", start_time="12:30", lat=48.8605, lng=2.3270),
                    _item(title="Luxembourg Gardens", category="park", role="walking_route", start_time="15:00", lat=48.8462, lng=2.3372),
                    _item(title="Dinner", category="restaurant", role="dinner", start_time="19:00", lat=48.8578, lng=2.3522),
                ],
            )
        ]
        prompt = "오르세는 꼭 넣어줘. 성당은 빼고 이동은 편했으면 좋겠어."
        brief = {"must_include": ["오르세 미술관"], "must_avoid": ["노트르담 대성당", "생트샤펠"], "source_text": prompt}

        evaluation = evaluate_plan(itinerary_days, brief, prompt=prompt, language="ko")

        self.assertFalse(any(failure["type"] == "must_avoid_violation" and failure.get("target") == "orsay" for failure in evaluation["failures"]))


if __name__ == "__main__":
    unittest.main()
