import unittest

from app.services.route_optimizer_service import _is_valid_meal_candidate, _role_key, _schedule_day


def _place_item(title: str, category: str, time_slot: str) -> dict:
    return {
        "time_slot": time_slot,
        "title": title,
        "place": {
            "name": title,
            "category": category,
            "coordinates": {"lat": 48.8566, "lng": 2.3522},
        },
        "description": "",
        "estimated_duration": "1시간",
    }


class RouteOptimizerServiceTests(unittest.TestCase):
    def test_iconic_landmarks_are_not_forced_into_night_view_outside_evening(self) -> None:
        self.assertEqual(_role_key(_place_item("Seine River", "landmark", "morning")), "landmark")
        self.assertEqual(_role_key(_place_item("Eiffel Tower", "landmark", "afternoon")), "landmark")
        self.assertEqual(_role_key(_place_item("Eiffel Tower", "landmark", "evening")), "night_view")

    def test_schedule_day_reassigns_swapped_slots_from_actual_time(self) -> None:
        items = [
            _place_item("Louvre Museum", "museum", "afternoon"),
            {
                "time_slot": "lunch",
                "title": "Le Café Marly 점심",
                "place": {
                    "name": "Le Café Marly",
                    "category": "cafe",
                    "coordinates": {"lat": 48.865, "lng": 2.337},
                },
                "description": "점심 식사",
                "estimated_duration": "1시간",
            },
            _place_item("Musee d'Orsay", "museum", "morning"),
        ]

        _schedule_day(items, "normal", "ko")

        self.assertEqual(items[0]["time_slot"], "morning")
        self.assertEqual(items[1]["time_slot"], "lunch")
        self.assertEqual(items[2]["time_slot"], "afternoon")
        self.assertEqual(items[0]["start_time"], "09:30")
        self.assertEqual(items[2]["start_time"], "13:15")

    def test_schedule_day_delays_start_before_evening_view_instead_of_padding_gap(self) -> None:
        items = [
            _place_item("Arc de Triomphe", "landmark", "morning"),
            _place_item("Eiffel Tower", "landmark", "evening"),
        ]
        items[0]["route_to_next"] = {
            "mode": "transit",
            "duration_seconds": 22 * 60,
            "rawDurationMinutes": 22,
            "bufferMinutes": 20,
            "totalTransferMinutes": 42,
            "restBufferReason": "환승 여유",
        }

        _schedule_day(items, "normal", "ko", {"night_view": True})

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["start_time"], "16:08")
        self.assertEqual(items[1]["title"], "Eiffel Tower")
        self.assertEqual(items[1]["start_time"], "18:00")

    def test_meal_candidate_rejects_landmark_and_accepts_real_restaurant(self) -> None:
        anchor = {"lat": 48.8566, "lng": 2.3522}
        used_names: set[str] = set()

        self.assertFalse(
            _is_valid_meal_candidate(
                {
                    "title": "Montmartre",
                    "place": {
                        "name": "Montmartre",
                        "category": "landmark",
                        "coordinates": {"lat": 48.8867, "lng": 2.3431},
                    },
                },
                anchor,
                used_names,
            )
        )
        self.assertTrue(
            _is_valid_meal_candidate(
                {
                    "title": "Cafe de Paris dinner",
                    "place": {
                        "name": "Cafe de Paris",
                        "category": "restaurant",
                        "coordinates": {"lat": 48.857, "lng": 2.3525},
                    },
                },
                anchor,
                used_names,
            )
        )

    def test_schedule_day_preserves_helper_blocks_as_gap_items(self) -> None:
        items = [
            {
                "time_slot": "afternoon",
                "title": "점심 전 자유 시간",
                "place": {
                    "name": "점심 전 자유 시간",
                    "category": "free_time",
                    "coordinates": None,
                },
                "description": "보조 여유 시간",
                "estimated_duration": "1시간",
            },
            _place_item("Cafe de Paris dinner", "restaurant", "evening"),
        ]

        _schedule_day(items, "slow", "ko")

        self.assertEqual(items[0]["itemKind"], "gap")
        self.assertEqual(items[1]["itemKind"], "stop")


if __name__ == "__main__":
    unittest.main()
