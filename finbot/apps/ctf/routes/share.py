"""Share Routes - OG image generation for social sharing"""

import hashlib
import logging
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from finbot.config import settings
from finbot.core.data.database import get_db
from finbot.core.data.models import UserBadge, UserChallengeProgress
from finbot.core.data.repositories import (
    BadgeRepository,
    ChallengeRepository,
    UserProfileRepository,
)

from .profile import calculate_level

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/share", tags=["share"])

# Cache directory for generated images
CACHE_DIR = Path(settings.DATA_DIR if hasattr(settings, "DATA_DIR") else ".") / "cache" / "share_cards"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get_cache_path(cache_key: str) -> Path:
    """Get cache file path for a given key"""
    return CACHE_DIR / f"{cache_key}.png"


def _get_font(size: int, bold: bool = False):
    """Get a font, trying multiple paths for cross-platform support."""
    from PIL import ImageFont

    # Font paths to try (macOS, Linux, Windows)
    font_paths = [
        # macOS
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSText.ttf",
        "/Library/Fonts/Arial.ttf",
        # Linux
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        # Windows
        "C:/Windows/Fonts/arial.ttf",
    ]

    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue

    # Fall back to default
    return ImageFont.load_default(size=size)


def generate_profile_card(
    username: str,
    avatar_emoji: str,
    bio: str,
    level: int,
    level_title: str,
    total_points: int,
    badges_earned: int,
    challenges_completed: int,
    completion_percentage: int,
) -> bytes:
    """Generate a profile share card using Pillow"""
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        logger.error("Pillow not installed. Run: pip install Pillow")
        raise HTTPException(status_code=500, detail="Image generation not available") from exc

    # Card dimensions (1200x630 for OG image standard)
    width, height = 1200, 630

    # Create image with dark background
    img = Image.new("RGB", (width, height), (10, 10, 15))
    draw = ImageDraw.Draw(img)

    # Draw gradient background
    for y in range(height):
        # Dark gradient from top to bottom
        r = 8 + int(y * 0.015)
        g = 8 + int(y * 0.02)
        b = 12 + int(y * 0.025)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    # Add cyan accent glow at top-left
    for i in range(200):
        alpha = int((1 - i / 200) * 25)
        draw.ellipse([-100 - i, -100 - i, 200 + i, 200 + i], fill=(alpha, int(alpha * 0.8), int(alpha * 0.5)))

    # Add purple accent glow at bottom-right
    for i in range(150):
        alpha = int((1 - i / 150) * 15)
        draw.ellipse([width - 150 - i, height - 100 - i, width + i, height + i], fill=(int(alpha * 0.5), alpha // 4, alpha))

    # Draw decorative grid pattern (subtle)
    for x in range(0, width, 50):
        draw.line([(x, 0), (x, height)], fill=(20, 20, 25), width=1)
    for y in range(0, height, 50):
        draw.line([(0, y), (width, y)], fill=(20, 20, 25), width=1)

    # Load fonts
    font_large = _get_font(44, bold=True)
    font_medium = _get_font(28)
    font_small = _get_font(20)
    font_xl = _get_font(56, bold=True)
    font_stat = _get_font(36, bold=True)

    # Try to load and paste FinBot logo
    logo_path = Path(__file__).parent.parent.parent.parent / "static" / "images" / "common" / "finbot.png"
    try:
        logo = Image.open(logo_path).convert("RGBA")
        logo = logo.resize((70, 70), Image.Resampling.LANCZOS)
        # Create a circular mask
        mask = Image.new("L", (70, 70), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse([0, 0, 70, 70], fill=255)
        # Draw cyan ring behind logo
        draw.ellipse([35, 25, 115, 105], fill=(0, 212, 255))
        draw.ellipse([40, 30, 110, 100], fill=(15, 15, 20))
        img.paste(logo, (40, 30), mask)
    except (OSError, IOError):
        # Draw fallback circle if logo not found
        draw.ellipse([40, 30, 110, 100], fill=(0, 212, 255))

    # Draw "FINBOT CTF" header
    draw.text((130, 45), "FINBOT", font=font_medium, fill=(255, 255, 255))
    draw.text((245, 52), "CTF", font=_get_font(16), fill=(0, 212, 255))

    # Draw OWASP ASI text
    draw.text((130, 80), "OWASP ASI", font=_get_font(14), fill=(100, 116, 139))

    # Main content area
    content_x = 80
    content_y = 150

    # Avatar section with gradient ring
    avatar_x, avatar_y = content_x + 80, content_y + 120
    
    # Draw gradient ring
    for r in range(85, 75, -1):
        progress = (85 - r) / 10
        color = (
            int(0 + progress * 124),  # cyan to purple
            int(212 - progress * 154),
            int(255 - progress * 18),
        )
        draw.ellipse(
            [avatar_x - r, avatar_y - r, avatar_x + r, avatar_y + r],
            outline=color,
            width=1,
        )
    
    # Inner circle
    draw.ellipse(
        [avatar_x - 70, avatar_y - 70, avatar_x + 70, avatar_y + 70],
        fill=(21, 21, 32),
    )

    # Avatar letter
    avatar_text = username[0].upper() if username else "?"
    try:
        bbox = draw.textbbox((0, 0), avatar_text, font=font_xl)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        draw.text(
            (avatar_x - text_width // 2, avatar_y - text_height // 2 - 8),
            avatar_text,
            font=font_xl,
            fill=(0, 212, 255),
        )
    except (OSError, IOError):
        pass

    # Username and info (right of avatar)
    info_x = avatar_x + 120
    info_y = content_y + 50

    # Username
    draw.text((info_x, info_y), f"@{username}", font=font_large, fill=(255, 255, 255))

    # Level badge with background
    level_text = f"Lvl {level} · {level_title}"
    try:
        level_bbox = draw.textbbox((0, 0), level_text, font=font_medium)
        level_width = level_bbox[2] - level_bbox[0]
        draw.rounded_rectangle(
            [info_x - 12, info_y + 52, info_x + level_width + 24, info_y + 98],
            radius=10,
            fill=(124, 58, 237, 40),
            outline=(124, 58, 237),
        )
    except (OSError, IOError, TypeError):
        pass
    draw.text((info_x + 6, info_y + 60), level_text, font=font_medium, fill=(167, 139, 250))

    # Bio
    bio_display = (bio[:50] + "...") if len(bio) > 50 else bio
    draw.text((info_x, info_y + 110), bio_display, font=font_small, fill=(148, 163, 184))

    # Stats section at bottom
    stats_y = 420
    stats = [
        (f"{total_points:,}", "Points", (0, 212, 255)),
        (str(badges_earned), "Badges", (124, 58, 237)),
        (f"{completion_percentage}%", "Complete", (6, 255, 165)),
        (str(challenges_completed), "Challenges", (255, 184, 0)),
    ]

    # Draw stats background bar
    draw.rounded_rectangle(
        [60, stats_y - 20, width - 60, stats_y + 100],
        radius=16,
        fill=(20, 20, 28),
        outline=(40, 40, 50),
    )

    stat_width = (width - 160) // 4
    for i, (value, label, color) in enumerate(stats):
        x = 80 + i * stat_width + stat_width // 2
        
        # Value
        try:
            bbox = draw.textbbox((0, 0), value, font=font_stat)
            val_width = bbox[2] - bbox[0]
            draw.text((x - val_width // 2, stats_y), value, font=font_stat, fill=color)
        except (OSError, IOError):
            draw.text((x - 30, stats_y), value, font=font_stat, fill=color)
        
        # Label
        try:
            bbox = draw.textbbox((0, 0), label, font=font_small)
            label_width = bbox[2] - bbox[0]
            draw.text((x - label_width // 2, stats_y + 45), label, font=font_small, fill=(100, 116, 139))
        except (OSError, IOError):
            draw.text((x - 30, stats_y + 45), label, font=font_small, fill=(100, 116, 139))

    # Footer line
    draw.line([(60, 550), (width - 60, 550)], fill=(40, 40, 50), width=1)

    # Footer text
    draw.text((60, 570), "owasp-finbot-ctf.org", font=font_small, fill=(80, 80, 100))

    # Hashtags
    hashtags = "#OWASPGenAISecurityProject"
    try:
        bbox = draw.textbbox((0, 0), hashtags, font=font_small)
        tag_width = bbox[2] - bbox[0]
        draw.text((width - 60 - tag_width, 570), hashtags, font=font_small, fill=(0, 212, 255))
    except (OSError, IOError):
        pass

    # Convert to bytes
    buffer = BytesIO()
    img.save(buffer, format="PNG", optimize=True)
    buffer.seek(0)
    return buffer.getvalue()


@router.get("/profile/{username}/card.png")
async def get_profile_card(
    username: str,
    db: Session = Depends(get_db),
):
    """Generate and return a profile share card image"""
    # Fetch profile data
    profile_repo = UserProfileRepository(db)
    profile, user = profile_repo.get_public_profile_with_user(username)

    if not profile or not user:
        raise HTTPException(status_code=404, detail="Profile not found")

    # Get stats
    completed_progress = (
        db.query(UserChallengeProgress)
        .filter(
            UserChallengeProgress.namespace == user.namespace,
            UserChallengeProgress.user_id == profile.user_id,
            UserChallengeProgress.status == "completed",
        )
        .all()
    )

    earned_badges = (
        db.query(UserBadge)
        .filter(
            UserBadge.namespace == user.namespace,
            UserBadge.user_id == profile.user_id,
        )
        .all()
    )

    # Calculate points
    challenge_repo = ChallengeRepository(db)
    badge_repo = BadgeRepository(db)

    challenge_points = challenge_repo.get_effective_points(completed_progress)
    earned_badge_ids = [b.badge_id for b in earned_badges]
    badge_points = badge_repo.get_total_points(earned_badge_ids)
    hints_cost = sum(p.hints_cost for p in completed_progress)
    total_points = challenge_points + badge_points - hints_cost

    # Completion percentage
    total_challenges = len(challenge_repo.list_challenges())
    completion_pct = (
        int((len(completed_progress) / total_challenges) * 100)
        if total_challenges > 0
        else 0
    )

    # Level
    level, level_title = calculate_level(total_points)

    # Generate cache key
    cache_data = f"{username}:{total_points}:{len(earned_badges)}:{len(completed_progress)}"
    cache_key = hashlib.md5(cache_data.encode()).hexdigest()
    cache_path = get_cache_path(cache_key)

    # Check cache
    if cache_path.exists():
        return Response(
            content=cache_path.read_bytes(),
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=300"},
        )

    # Generate image
    image_bytes = generate_profile_card(
        username=profile.username,
        avatar_emoji=profile.avatar_emoji or "🦊",
        bio=profile.bio or "AI Security Enthusiast",
        level=level,
        level_title=level_title,
        total_points=total_points,
        badges_earned=len(earned_badges),
        challenges_completed=len(completed_progress),
        completion_percentage=completion_pct,
    )

    # Save to cache
    cache_path.write_bytes(image_bytes)

    return Response(
        content=image_bytes,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.get("/badge/{badge_id}/card.png")
async def get_badge_card(
    badge_id: str,
    db: Session = Depends(get_db),
):
    """Generate and return a badge share card image"""
    badge_repo = BadgeRepository(db)
    badge = badge_repo.get_badge(badge_id)

    if not badge:
        raise HTTPException(status_code=404, detail="Badge not found")

    # Generate badge share card
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="Image generation not available") from exc

    width, height = 1200, 630
    img = Image.new("RGB", (width, height), (10, 10, 15))
    draw = ImageDraw.Draw(img)

    # Draw gradient background
    for y in range(height):
        r = 8 + int(y * 0.015)
        g = 8 + int(y * 0.02)
        b = 12 + int(y * 0.025)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    # Rarity colors (RGB tuples)
    rarity_colors = {
        "common": (55, 65, 81),
        "rare": (59, 130, 246),
        "epic": (168, 85, 247),
        "legendary": (245, 158, 11),
    }
    color = rarity_colors.get(badge.rarity, (55, 65, 81))

    # Add rarity-based accent glow
    if badge.rarity == "legendary":
        for i in range(150):
            alpha = int((1 - i / 150) * 20)
            draw.ellipse([width // 2 - 200 - i, 100 - i, width // 2 + 200 + i, 340 + i], fill=(alpha, int(alpha * 0.6), 0))
    elif badge.rarity == "epic":
        for i in range(150):
            alpha = int((1 - i / 150) * 20)
            draw.ellipse([width // 2 - 200 - i, 100 - i, width // 2 + 200 + i, 340 + i], fill=(int(alpha * 0.6), alpha // 4, alpha))
    elif badge.rarity == "rare":
        for i in range(150):
            alpha = int((1 - i / 150) * 20)
            draw.ellipse([width // 2 - 200 - i, 100 - i, width // 2 + 200 + i, 340 + i], fill=(0, int(alpha * 0.4), alpha))

    # Draw decorative grid pattern (subtle)
    for x in range(0, width, 50):
        draw.line([(x, 0), (x, height)], fill=(20, 20, 25), width=1)
    for y in range(0, height, 50):
        draw.line([(0, y), (width, y)], fill=(20, 20, 25), width=1)

    # Load fonts
    font_xl = _get_font(56, bold=True)
    font_large = _get_font(44, bold=True)
    font_medium = _get_font(28)
    font_small = _get_font(20)

    # Try to load and paste FinBot logo
    logo_path = Path(__file__).parent.parent.parent.parent / "static" / "images" / "common" / "finbot.png"
    try:
        logo = Image.open(logo_path).convert("RGBA")
        logo = logo.resize((60, 60), Image.Resampling.LANCZOS)
        mask = Image.new("L", (60, 60), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse([0, 0, 60, 60], fill=255)
        draw.ellipse([35, 25, 105, 95], fill=(0, 212, 255))
        draw.ellipse([40, 30, 100, 90], fill=(15, 15, 20))
        img.paste(logo, (40, 30), mask)
    except (OSError, IOError):
        draw.ellipse([40, 30, 100, 90], fill=(0, 212, 255))

    # Draw "FINBOT CTF" header
    draw.text((120, 40), "FINBOT", font=font_medium, fill=(255, 255, 255))
    draw.text((235, 47), "CTF", font=_get_font(16), fill=(0, 212, 255))
    draw.text((120, 72), "OWASP ASI", font=_get_font(14), fill=(100, 116, 139))

    # Draw badge circle with glow effect
    center_x, center_y = width // 2, 230

    # Outer glow for rare+ badges
    if badge.rarity in ("rare", "epic", "legendary"):
        for r in range(120, 100, -2):
            alpha = int((120 - r) * 3)
            glow_color = (
                min(255, color[0] + alpha),
                min(255, color[1] + alpha),
                min(255, color[2] + alpha),
            )
            draw.ellipse(
                [center_x - r, center_y - r, center_x + r, center_y + r],
                outline=glow_color,
                width=2,
            )

    # Main badge circle with gradient ring
    for r_val in range(95, 85, -1):
        progress = (95 - r_val) / 10
        ring_color = (
            int(color[0] * (1 - progress * 0.3)),
            int(color[1] * (1 - progress * 0.3)),
            int(color[2] * (1 - progress * 0.3)),
        )
        draw.ellipse(
            [center_x - r_val, center_y - r_val, center_x + r_val, center_y + r_val],
            outline=ring_color,
            width=1,
        )
    
    draw.ellipse(
        [center_x - 80, center_y - 80, center_x + 80, center_y + 80],
        fill=(21, 21, 32),
    )

    # Badge icon (first letter)
    icon_text = badge.title[0].upper() if badge.title else "?"
    try:
        bbox = draw.textbbox((0, 0), icon_text, font=font_xl)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        draw.text(
            (center_x - text_width // 2, center_y - text_height // 2 - 5),
            icon_text,
            font=font_xl,
            fill=color,
        )
    except (OSError, IOError):
        pass

    # Badge title
    try:
        title_bbox = draw.textbbox((0, 0), badge.title, font=font_large)
        title_width = title_bbox[2] - title_bbox[0]
        draw.text(
            ((width - title_width) // 2, 370),
            badge.title,
            font=font_large,
            fill=(255, 255, 255),
        )
    except (OSError, IOError):
        pass

    # Rarity badge with background
    rarity_text = f"{badge.rarity.upper()} · {badge.points} pts"
    try:
        rarity_bbox = draw.textbbox((0, 0), rarity_text, font=font_medium)
        rarity_width = rarity_bbox[2] - rarity_bbox[0]
        rarity_x = (width - rarity_width) // 2
        draw.rounded_rectangle(
            [rarity_x - 15, 425, rarity_x + rarity_width + 15, 465],
            radius=8,
            fill=(color[0] // 6, color[1] // 6, color[2] // 6),
            outline=color,
        )
        draw.text(
            (rarity_x, 430),
            rarity_text,
            font=font_medium,
            fill=color,
        )
    except (OSError, IOError, TypeError):
        pass

    # Description
    if badge.description:
        desc = (badge.description[:70] + "...") if len(badge.description) > 70 else badge.description
        try:
            desc_bbox = draw.textbbox((0, 0), desc, font=font_small)
            desc_width = desc_bbox[2] - desc_bbox[0]
            draw.text(
                ((width - desc_width) // 2, 490),
                desc,
                font=font_small,
                fill=(148, 163, 184),
            )
        except (OSError, IOError):
            pass

    # Footer line
    draw.line([(60, 550), (width - 60, 550)], fill=(40, 40, 50), width=1)

    # Footer text
    draw.text((60, 570), "owasp-finbot-ctf.org", font=font_small, fill=(80, 80, 100))

    # Hashtags
    hashtags = "#OWASPGenAISecurityProject"
    try:
        bbox = draw.textbbox((0, 0), hashtags, font=font_small)
        tag_width = bbox[2] - bbox[0]
        draw.text((width - 60 - tag_width, 570), hashtags, font=font_small, fill=color)
    except (OSError, IOError):
        pass

    buffer = BytesIO()
    img.save(buffer, format="PNG", optimize=True)
    buffer.seek(0)

    return Response(
        content=buffer.getvalue(),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )
