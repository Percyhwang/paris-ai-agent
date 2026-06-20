import unittest

from app.services.daily_quality_validator_service import evaluate_itinerary_quality


def _item(
    *,
    title: str,
    category: str,
    role: str,
    start_time: str,
    time_slot: str,
) -> dict:
    return {
        "id": f"item-{title}-{start_time}",
        "title": title,
        "role": role,
        "time_slot": time_slot,
        "start_time": start_time,
        "description": f"{title} supports the day rhythm.",
        "place": {
            "place_id": title.lower().replace(" ", "-"),
            "name": title,
            "category": category,
            "role": role,
            "coordinates": {"lat": 48.8566, "lng": 2.3522},
        },
    }


def _day(day_number: int, theme: str, items: list[dict]) -> dict:
    return {
        "day_number": day_number,
        "title": theme,
        "theme": theme,
        "dayTheme": theme,
        "items": items,
    }


class DailyQualityValidatorServiceTests(unittest.TestCase):
    def test_local_neighborhood_day_counts_as_main_activity_when_local_is_requested(self) -> None:
        itinerary_days = [
            _day(
                1,
                "Marais and Saint-Germain local day",
                [
                    _item(title="Saint-Germain-des-Pres", category="neighborhood", role="walking_route", start_time="10:00", time_slot="morning"),
                    _item(title="Lunch", category="restaurant", role="lunch", start_time="12:30", time_slot="lunch"),
                    _item(title="Le Marais", category="neighborhood", role="walking_route", start_time="15:00", time_slot="afternoon"),
                    _item(title="Dinner", category="restaurant", role="dinner", start_time="18:45", time_slot="evening"),
                ],
            )
        ]

        result = evaluate_itinerary_quality(
            itinerary_days,
            {"travel_style": ["local"], "source_text": "로컬 동네 위주로 천천히"},
            prompt="로컬 동네 위주로 천천히",
            language="ko",
        )
        issue_codes = {issue["code"] for issue in result["days"][0]["issue_details"]}

        self.assertNotIn("main_activity_missing", issue_codes)
        self.assertTrue(result["days"][0]["quality_checks"]["main_activity_exists"])

    def test_brunch_request_allows_late_morning_meal_without_lunch_timing_error(self) -> None:
        itinerary_days = [
            _day(
                1,
                "Brunch and evening view day",
                [
                    _item(title="Brunch Cafe", category="cafe", role="lunch", start_time="11:15", time_slot="lunch"),
                    _item(title="Palais Royal", category="landmark", role="landmark", start_time="13:00", time_slot="afternoon"),
                    _item(title="Dinner", category="restaurant", role="dinner", start_time="18:45", time_slot="evening"),
                    _item(title="Seine Walk", category="neighborhood", role="walking_route", start_time="20:00", time_slot="evening"),
                ],
            )
        ]

        result = evaluate_itinerary_quality(
            itinerary_days,
            {"meal_preference": ["brunch"], "source_text": "브런치 이후에 시작하고 싶어"},
            prompt="브런치 이후에 시작하고 싶어",
            language="ko",
        )
        issue_codes = {issue["code"] for issue in result["days"][0]["issue_details"]}

        self.assertNotIn("lunch_timing_bad", issue_codes)
        self.assertTrue(result["days"][0]["quality_checks"]["meal_timing_ok"])

    def test_family_trip_flags_nightlife_stop(self) -> None:
        itinerary_days = [
            _day(
                1,
                "Family-friendly Left Bank day",
                [
                    _item(title="Luxembourg Gardens", category="park", role="walking_route", start_time="10:00", time_slot="morning"),
                    _item(title="Lunch", category="restaurant", role="lunch", start_time="12:30", time_slot="lunch"),
                    _item(title="Notre-Dame", category="cathedral", role="landmark", start_time="15:00", time_slot="afternoon"),
                    _item(title="Jazz Club", category="bar", role="night_activity", start_time="21:15", time_slot="night"),
                ],
            )
        ]

        result = evaluate_itinerary_quality(itinerary_days, {"travel_style": ["family"], "source_text": "가족 여행"}, prompt="가족 여행", language="ko")
        day = result["days"][0]
        issue_codes = {issue["code"] for issue in day["issue_details"]}

        self.assertIn("family_unsuitable_stop", issue_codes)
        self.assertFalse(day["quality_checks"]["family_friendly_ok"])

    def test_museum_limit_per_day_is_enforced(self) -> None:
        itinerary_days = [
            _day(
                1,
                "Museum day with too much art",
                [
                    _item(title="Louvre Museum", category="museum", role="museum_or_gallery", start_time="09:30", time_slot="morning"),
                    _item(title="Musee d'Orsay", category="museum", role="museum_or_gallery", start_time="13:30", time_slot="afternoon"),
                    _item(title="Lunch", category="restaurant", role="lunch", start_time="12:15", time_slot="lunch"),
                    _item(title="Dinner", category="restaurant", role="dinner", start_time="19:00", time_slot="evening"),
                ],
            )
        ]

        result = evaluate_itinerary_quality(
            itinerary_days,
            {"travel_style": ["museum", "art"], "museum_limit_per_day": 1, "source_text": "하루 미술관 한 곳만"},
            prompt="하루 미술관 한 곳만",
            language="ko",
        )
        day = result["days"][0]
        issue_codes = {issue["code"] for issue in day["issue_details"]}

        self.assertIn("museum_density_violation", issue_codes)
        self.assertFalse(day["quality_checks"]["museum_density_ok"])

    def test_local_mood_request_flags_tourist_heavy_day(self) -> None:
        itinerary_days = [
            _day(
                1,
                "Local mood request but classic heavy route",
                [
                    _item(title="Eiffel Tower", category="landmark", role="landmark", start_time="09:30", time_slot="morning"),
                    _item(title="Louvre Museum", category="museum", role="museum_or_gallery", start_time="11:30", time_slot="morning"),
                    _item(title="Lunch", category="restaurant", role="lunch", start_time="13:00", time_slot="lunch"),
                    _item(title="Galeries Lafayette", category="shopping", role="shopping", start_time="15:00", time_slot="afternoon"),
                    _item(title="Arc de Triomphe", category="landmark", role="landmark", start_time="19:30", time_slot="evening"),
                ],
            )
        ]

        result = evaluate_itinerary_quality(
            itinerary_days,
            {"travel_style": ["local"], "source_text": "로컬하고 너무 관광지스럽지 않게"},
            prompt="로컬하고 너무 관광지스럽지 않게",
            language="ko",
        )
        day = result["days"][0]
        issue_codes = {issue["code"] for issue in day["issue_details"]}

        self.assertIn("touristiness_mismatch", issue_codes)
        self.assertFalse(day["quality_checks"]["local_style_ok"])

    def test_cafe_focused_day_with_two_real_experiences_is_not_marked_meal_heavy(self) -> None:
        itinerary_days = [
            _day(
                1,
                "Cafe and walk day",
                [
                    _item(title="Montmartre Walk", category="neighborhood", role="walking_route", start_time="10:00", time_slot="morning"),
                    _item(title="Lunch Bistro", category="restaurant", role="lunch", start_time="12:30", time_slot="lunch"),
                    _item(title="Afternoon Cafe", category="cafe", role="cafe_break", start_time="15:00", time_slot="afternoon"),
                    _item(title="Marais Boutiques", category="shopping", role="shopping", start_time="16:20", time_slot="afternoon"),
                    _item(title="Dinner", category="restaurant", role="dinner", start_time="19:00", time_slot="evening"),
                ],
            )
        ]

        result = evaluate_itinerary_quality(
            itinerary_days,
            {"travel_style": ["cafe", "foodie"], "source_text": "카페 투어와 감성 산책"},
            prompt="카페 투어와 감성 산책",
            language="ko",
        )
        issue_codes = {issue["code"] for issue in result["days"][0]["issue_details"]}

        self.assertNotIn("meal_heavy_day", issue_codes)

    def test_art_trip_can_mix_art_days_with_night_view_days(self) -> None:
        itinerary_days = [
            _day(
                1,
                "Orsay and river night",
                [
                    _item(title="Musee d'Orsay", category="museum", role="museum_or_gallery", start_time="10:00", time_slot="morning"),
                    _item(title="Lunch", category="restaurant", role="lunch", start_time="12:30", time_slot="lunch"),
                    _item(title="Seine Walk", category="neighborhood", role="walking_route", start_time="16:00", time_slot="afternoon"),
                    _item(title="Dinner", category="restaurant", role="dinner", start_time="19:00", time_slot="evening"),
                ],
            ),
            _day(
                2,
                "Eiffel night view day",
                [
                    _item(title="Luxembourg Gardens", category="park", role="walking_route", start_time="10:30", time_slot="morning"),
                    _item(title="Lunch", category="restaurant", role="lunch", start_time="12:40", time_slot="lunch"),
                    _item(title="Saint-Germain", category="neighborhood", role="walking_route", start_time="15:30", time_slot="afternoon"),
                    _item(title="Dinner", category="restaurant", role="dinner", start_time="18:40", time_slot="evening"),
                    _item(title="Eiffel Tower", category="landmark", role="landmark", start_time="20:00", time_slot="evening"),
                ],
            ),
            _day(
                3,
                "Louvre and dinner day",
                [
                    _item(title="Louvre Museum", category="museum", role="museum_or_gallery", start_time="10:00", time_slot="morning"),
                    _item(title="Lunch", category="restaurant", role="lunch", start_time="12:35", time_slot="lunch"),
                    _item(title="Tuileries Garden", category="park", role="walking_route", start_time="15:30", time_slot="afternoon"),
                    _item(title="Dinner", category="restaurant", role="dinner", start_time="19:00", time_slot="evening"),
                ],
            ),
            _day(
                4,
                "Arc night close",
                [
                    _item(title="Palais Royal", category="landmark", role="landmark", start_time="10:30", time_slot="morning"),
                    _item(title="Lunch", category="restaurant", role="lunch", start_time="12:45", time_slot="lunch"),
                    _item(title="Seine Walk", category="neighborhood", role="walking_route", start_time="16:00", time_slot="afternoon"),
                    _item(title="Dinner", category="restaurant", role="dinner", start_time="18:45", time_slot="evening"),
                    _item(title="Arc de Triomphe", category="landmark", role="landmark", start_time="20:00", time_slot="evening"),
                ],
            ),
        ]

        result = evaluate_itinerary_quality(
            itinerary_days,
            {"travel_style": ["museum", "art", "night_view"], "source_text": "미술관이랑 야경 중심"},
            prompt="미술관이랑 야경 중심",
            language="ko",
        )
        day_issue_codes = [
            {issue["code"] for issue in day["issue_details"]}
            for day in result["days"]
        ]

        self.assertTrue(all("art_focus_missing" not in issue_codes for issue_codes in day_issue_codes))
        self.assertIn("art", result["matched_concepts"])
        self.assertIn("night_view", result["matched_concepts"])

    def test_jazz_bar_after_dinner_is_not_flagged_as_restaurant_chain(self) -> None:
        itinerary_days = [
            _day(
                1,
                "Indoor culture and jazz night",
                [
                    _item(title="Musee d'Orsay", category="museum", role="museum_or_gallery", start_time="10:00", time_slot="morning"),
                    _item(title="Lunch", category="restaurant", role="lunch", start_time="12:30", time_slot="lunch"),
                    _item(title="Sainte-Chapelle", category="cathedral", role="landmark", start_time="15:00", time_slot="afternoon"),
                    _item(title="Dinner", category="restaurant", role="dinner", start_time="19:00", time_slot="evening"),
                    _item(title="Jazz Club", category="bar", role="night_activity", start_time="21:00", time_slot="night"),
                ],
            )
        ]

        result = evaluate_itinerary_quality(
            itinerary_days,
            {"travel_style": ["jazz", "nightlife", "indoor"], "meal_preference": ["jazz_bar"], "source_text": "재즈바 같은 분위기"},
            prompt="재즈바 같은 분위기",
            language="ko",
        )
        issue_codes = {issue["code"] for issue in result["days"][0]["issue_details"]}

        self.assertNotIn("consecutive_restaurant_chain", issue_codes)

    def test_lunch_and_dinner_with_long_gap_are_not_flagged_as_restaurant_chain(self) -> None:
        itinerary_days = [
            _day(
                1,
                "Museum and evening walk day",
                [
                    _item(title="Cafe Start", category="cafe", role="cafe_break", start_time="10:00", time_slot="morning"),
                    _item(title="Museum Stop", category="museum", role="museum_or_gallery", start_time="11:00", time_slot="morning"),
                    _item(title="Lunch", category="restaurant", role="lunch", start_time="12:45", time_slot="lunch"),
                    _item(title="Dinner", category="restaurant", role="dinner", start_time="18:40", time_slot="evening"),
                    _item(title="Seine Walk", category="neighborhood", role="walking_route", start_time="20:00", time_slot="evening"),
                ],
            )
        ]

        result = evaluate_itinerary_quality(
            itinerary_days,
            {"travel_style": ["indoor"], "source_text": "실내 위주 여행"},
            prompt="실내 위주 여행",
            language="ko",
        )
        issue_codes = {issue["code"] for issue in result["days"][0]["issue_details"]}

        self.assertNotIn("consecutive_restaurant_chain", issue_codes)


if __name__ == "__main__":
    unittest.main()
