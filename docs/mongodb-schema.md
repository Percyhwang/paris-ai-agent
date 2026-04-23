# MongoDB Collection Design

## users

Stores Google OAuth profile and service preferences.

```json
{
  "_id": "ObjectId",
  "google_id": "string unique",
  "email": "string unique",
  "name": "string",
  "profile_image": "string|null",
  "preferences": {
    "travel_style": ["string"],
    "favorite_categories": ["string"],
    "budget_currency": "EUR",
    "language": "ko"
  },
  "trips": ["trip_id"],
  "refresh_token_hash": "string",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

## trip_plans

Stores one trip summary per generated or manually created Paris travel plan.

```json
{
  "_id": "ObjectId",
  "user_id": "string",
  "trip_title": "string",
  "prompt": "string|null",
  "start_date": "datetime|null",
  "end_date": "datetime|null",
  "total_days": "number",
  "style_tags": ["classic", "museum"],
  "status": "draft|generated",
  "route_summary": "string|null",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

## itinerary_day

Stores timeline data per trip day.

```json
{
  "_id": "ObjectId",
  "trip_id": "string",
  "user_id": "string",
  "day_number": 1,
  "date": "datetime|null",
  "title": "string",
  "route_summary": "string",
  "items": [
    {
      "id": "uuid",
      "time_slot": "morning|lunch|afternoon|evening",
      "start_time": "09:30",
      "title": "string",
      "place": {
        "place_id": "string|null",
        "name": "string",
        "category": "string",
        "coordinates": { "lat": 48.8584, "lng": 2.2945 }
      },
      "description": "string",
      "estimated_duration": "string"
    }
  ],
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

## reservation_summary

Stores reservation records linked to a trip.

```json
{
  "_id": "ObjectId",
  "trip_id": "string",
  "user_id": "string",
  "reservation_type": "hotel|flight|ticket|activity",
  "provider": "string",
  "title": "string",
  "start_date": "date|string|null",
  "end_date": "date|string|null",
  "price": 0,
  "currency": "EUR",
  "status": "pending|confirmed|canceled",
  "booking_reference": "string|null",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

## budget_summary

Stores one mutable budget document per trip.

```json
{
  "_id": "ObjectId",
  "trip_id": "string unique",
  "attraction_total": 0,
  "hotel_total": 0,
  "custom_expenses": [
    {
      "id": "uuid",
      "category": "attraction|hotel|custom|other",
      "title": "string",
      "amount": 0,
      "currency": "EUR",
      "day_number": "number|null",
      "note": "string|null"
    }
  ],
  "grand_total": 0,
  "currency": "EUR",
  "last_updated": "datetime"
}
```

## diary_entry

Stores user-created or LLM-assisted travel diary entries.

```json
{
  "_id": "ObjectId",
  "user_id": "string",
  "trip_id": "string",
  "entry_date": "date|string",
  "photo_urls": ["string"],
  "emotion_tags": ["string"],
  "notes": "string",
  "place": "string|null",
  "title": "string",
  "generated_diary_text": "string",
  "mood_keywords": ["string"],
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

## place_catalog

Stores searchable Paris landmark catalog data. Seed data is inserted on startup if the collection is empty.

```json
{
  "_id": "ObjectId",
  "slug": "string unique",
  "name": "string",
  "category": "landmark|museum|cathedral|park|neighborhood",
  "coordinates": { "lat": 48.8584, "lng": 2.2945 },
  "image_url": "string",
  "short_description": "string",
  "full_description": "string",
  "history": "string",
  "photo_spot_tips": ["string"],
  "estimated_visit_duration": "string",
  "admission_fee": "string|null",
  "location": "string",
  "tags": ["string"],
  "popularity": 100
}
```

## weather_cache

Optional cache collection for future production weather API responses.

```json
{
  "_id": "ObjectId",
  "cache_key": "paris:forecast:7",
  "payload": {},
  "expires_at": "datetime"
}
```
