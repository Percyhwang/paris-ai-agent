import json
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure


USERNAME = "givemechanceplz30_db_user"
PASSWORD = "rudwo001219"
CLUSTER_URL = "cluster0.k32txaz.mongodb.net"


MONGO_URI = (
    f"mongodb+srv://{USERNAME}:{PASSWORD}@{CLUSTER_URL}/"
    "?retryWrites=true&w=majority&appName=Cluster0"
)

DB_NAME = "paris_trip"
COLLECTION_NAME = "places"
JSON_PATH = "paris_places_clean.json"


def main() -> None:
    client = MongoClient(MONGO_URI)
    try:
        client.admin.command("ping")
        print("MongoDB Atlas 연결 성공")
    except ConnectionFailure as exc:
        print("MongoDB Atlas 연결 실패:", exc)
        return

    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]

    with open(JSON_PATH, "r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError("paris_places_clean.json 이 리스트 형태가 아닙니다.")

    print(f"JSON에서 {len(data)}개 문서를 읽었습니다.")

    if data:
        result = collection.insert_many(data)
        print(f"Atlas에 {len(result.inserted_ids)}개 문서를 업로드했습니다.")
    else:
        print("업로드할 문서가 없습니다.")

    client.close()


if __name__ == "__main__":
    main()

