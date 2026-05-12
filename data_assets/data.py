import json

INPUT_FILE = "paris_osm.geojson"
OUTPUT_FILE = "paris_places_clean.json"

PARIS_LAT_MIN = 48.80
PARIS_LAT_MAX = 48.90
PARIS_LNG_MIN = 2.20
PARIS_LNG_MAX = 2.47

seen_names = set()
converted = []

with open(INPUT_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

for feature in data["features"]:
    props = feature.get("properties", {})
    geom = feature.get("geometry", {})

    name = props.get("name")
    if not name:
        continue

    coordinates = geom.get("coordinates")
    if not coordinates:
        continue

    lng, lat = coordinates

    # 파리 범위 필터
    if not (PARIS_LAT_MIN <= lat <= PARIS_LAT_MAX and
            PARIS_LNG_MIN <= lng <= PARIS_LNG_MAX):
        continue

    tourism = props.get("tourism")
    leisure = props.get("leisure")
    amenity = props.get("amenity")

    if tourism == "museum":
        category = "museum"
    elif tourism == "attraction":
        category = "landmark"
    elif leisure == "park":
        category = "park"
    elif amenity == "cafe":
        category = "cafe"
    else:
        continue

    # 너무 짧은 이름 제거
    if len(name) < 4:
        continue

    # 중복 제거
    if name in seen_names:
        continue
    seen_names.add(name)

    converted.append({
        "name": name,
        "category": category,
        "location": {
            "type": "Point",
            "coordinates": [lng, lat]
        },
        "source": "osm"
    })

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(converted, f, ensure_ascii=False, indent=2)

print(f"정제 완료: {len(converted)}개 저장")