from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Float
from sqlalchemy.orm import relationship
from .db import Base

from .config import _DEFAULT_SMPLX_MODEL


class ConvertRequest(BaseModel):
    folders      : Optional[list[str]] = Field(
        default=None,
        description="Danh sách tên folder (D0001B, D0002,...) trong output_smplerx/. "
                    "Bỏ trống → scan toàn bộ root."
    )
    merge_out    : Optional[str] = Field(
        default=None,
        description="Path file merge output (vd: amass_output/ALL_merged_s1_amass.npz)"
    )
    fps          : float  = Field(default=30.0,  description="Frame rate")
    gender       : str    = Field(default="neutral", pattern="^(neutral|male|female)$")
    zero_trans   : bool   = Field(default=False, description="Zero out translation")
    no_smooth_trans: bool = Field(default=False)
    no_fix_orient  : bool = Field(default=False)
    no_hands_mean  : bool = Field(default=False)
    smplx_model_path: str = Field(default=str(_DEFAULT_SMPLX_MODEL))
    smooth_pose  : bool   = Field(default=False)
    pose_window  : int    = Field(default=5)
    zero_legs    : bool   = Field(default=False)
    trim_idle    : bool   = Field(default=True)
    trim_threshold: float = Field(default=0.08)
    trim_pad     : int    = Field(default=2)
    stabilize    : bool   = Field(default=True)
    rotate_x     : float  = Field(default=-90.0)
    skip_existing: bool   = Field(default=False)
    no_merge     : bool   = Field(default=False)
    blender_bin  : Optional[str] = Field(
        default=None,
        description="Đường dẫn blender executable. Để trống sẽ tự tìm trong container (/usr/local/bin/blender)."
    )


class TranslateRequest(BaseModel):
    sentence: str

# ─── SQLAlchemy Models ────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    requests = relationship("TranslationRequest", back_populates="user")


class TranslationRequest(Base):
    __tablename__ = "translation_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True) # Allow anonymous for now if needed
    sentence = Column(String, nullable=False)
    videos = Column(String)  # Store as a comma-separated string or JSON
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="requests")
