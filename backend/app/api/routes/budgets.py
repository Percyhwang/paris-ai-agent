from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import get_current_user
from app.core.responses import api_ok
from app.db.mongodb import get_database
from app.schemas.budget import BudgetItemCreate, BudgetUpdate
from app.services.budget_service import add_budget_item, delete_budget_item, get_budget, update_budget

router = APIRouter()


@router.get("/{trip_id}/budget")
async def get_budget_route(
    trip_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> dict:
    return api_ok(await get_budget(db, current_user["id"], trip_id))


@router.put("/{trip_id}/budget")
async def put_budget_route(
    trip_id: str,
    payload: BudgetUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> dict:
    budget = await update_budget(db, current_user["id"], trip_id, payload)
    return api_ok(budget, "Budget updated")


@router.post("/{trip_id}/budget/items")
async def post_budget_item_route(
    trip_id: str,
    payload: BudgetItemCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> dict:
    budget = await add_budget_item(db, current_user["id"], trip_id, payload)
    return api_ok(budget, "Budget item added")


@router.delete("/{trip_id}/budget/items/{item_id}")
async def delete_budget_item_route(
    trip_id: str,
    item_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> dict:
    budget = await delete_budget_item(db, current_user["id"], trip_id, item_id)
    return api_ok(budget, "Budget item deleted")
