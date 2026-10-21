from fastapi import APIRouter, Cookie, HTTPException, Response
from typing import Optional

from core import bill, delivery_optimizer as dopt
from server.schemas import DeliveryOptimizeRequest
from server.state import store

router = APIRouter(prefix="/api/delivery", tags=["delivery"])


@router.post("/optimize")
def get_delivery_optimization(req: Optional[DeliveryOptimizeRequest] = None, forge_session: Optional[str] = Cookie(None)):
    session = store.get_or_create(forge_session)
    parts = session.get_active_parts()
    if not parts:
        raise HTTPException(status_code=400, detail="No active BOM build to optimize")

    fee = req.shipping_fee if req and req.shipping_fee is not None else dopt.DEFAULT_SHIPPING_FEE
    thresh = req.free_threshold if req and req.free_threshold is not None else dopt.FREE_SHIPPING_THRESHOLD

    analysis = dopt.analyze_sourcing_strategies(
        parts=parts,
        live=session.live,
        current_choice=session.choice,
        manual=session.manual,
        shipping_fee=fee,
        free_threshold=thresh,
    )
    return analysis


@router.post("/apply")
def apply_delivery_strategy(strategy: str, forge_session: Optional[str] = Cookie(None)):
    session = store.get_or_create(forge_session)
    parts = session.get_active_parts()
    analysis = dopt.analyze_sourcing_strategies(
        parts=parts,
        live=session.live,
        current_choice=session.choice,
        manual=session.manual,
    )
    strat = analysis.get(strategy)
    if not strat or "choice" not in strat:
        raise HTTPException(status_code=400, detail=f"Invalid strategy '{strategy}'")

    session.choice = strat["choice"]
    return {"status": "ok", "strategy": strategy, "choice": session.choice}


@router.get("/cart-csv")
def download_cart_csv(forge_session: Optional[str] = Cookie(None)):
    session = store.get_or_create(forge_session)
    parts = session.get_active_parts()
    label = session.get_build_label()
    b = bill.make(parts, session.live, session.choice, session.budget, label, session.manual)
    lines = b.get("lines", [])
    csv_str = dopt.export_cart_csv(lines, dopt.DEFAULT_SHIPPING_FEE, dopt.FREE_SHIPPING_THRESHOLD)
    filename = f"forge_multi_store_cart_{session.project}.csv"
    return Response(
        content=csv_str,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
