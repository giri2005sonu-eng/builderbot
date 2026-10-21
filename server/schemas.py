from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class SurveyAnswerRequest(BaseModel):
    answers: Dict[str, Any]
    step: Optional[int] = None


class SurveyRankRequest(BaseModel):
    answers: Optional[Dict[str, Any]] = None
    limit: int = Field(default=5, ge=1, le=20)
    hours_per_week: Optional[int] = Field(default=None, ge=1, le=80)
    deadline_weeks: Optional[int] = Field(default=None, ge=1, le=104)
    completed_project_ids: Optional[List[str]] = None


class RecommendationFeedbackContext(BaseModel):
    level: Optional[int] = Field(default=None, ge=1, le=5)
    role: Optional[str] = Field(default=None, max_length=40)


class SurveyFeedbackRequest(BaseModel):
    project_id: str
    signal: Literal["built", "too_hard", "too_easy", "not_interested"]
    context: RecommendationFeedbackContext = Field(default_factory=RecommendationFeedbackContext)


class CareerResearchRequest(BaseModel):
    query: str


class IdeaMatchRequest(BaseModel):
    text: str


class ResumeConfirmRequest(BaseModel):
    group: str
    index: int
    confirmed: bool


class BomGenerateRequest(BaseModel):
    project: Optional[str] = None
    budget: int = 3500
    bluetooth: bool = False
    custom_idea: Optional[str] = None
    skip_local: bool = False


class BomChoiceRequest(BaseModel):
    action: str = Field(..., description="'pick', 'manual', or 'reset'")
    part_id: Optional[str] = None
    url: Optional[str] = None
    price: Optional[float] = None
    name: Optional[str] = None


class DeliveryOptimizeRequest(BaseModel):
    shipping_fee: Optional[float] = None
    free_threshold: Optional[float] = None


class OptimizerSwapRequest(BaseModel):
    role: str
    swap_part_id: str


class GuidesResearchRequest(BaseModel):
    project_label: Optional[str] = None


class SpecsCompareRequest(BaseModel):
    part_name: str
    compare_with: Optional[List[str]] = None


class CartCheckRequest(BaseModel):
    url: str
    expected_price: float


class StateResponse(BaseModel):
    stage: str
    project: str
    budget: int
    bluetooth: bool
    survey_step: int
    survey_answers: Dict[str, Any]
    bom_origin: Optional[str]
    has_custom: bool
    has_res: bool
