"""
apps/throttles.py  —  shared throttle classes for the whole project.

Import from here in any view:
    from apps.throttles import AnonUploadThrottle, UserUploadThrottle, ...
"""
from rest_framework.throttling import SimpleRateThrottle, UserRateThrottle, AnonRateThrottle


# ── Upload throttles (heavy operations) ───────────────────────────────────────

class AnonUploadThrottle(SimpleRateThrottle):
    """
    Completely blocks anonymous uploads.
    Anonymous users get 0 upload slots — they must log in.
    Returns 429 with a message telling them to authenticate.
    """
    scope = "anon_upload"

    def get_cache_key(self, request, view):
        # Always throttle anon users trying to upload
        if request.user and request.user.is_authenticated:
            return None   # let UserUploadThrottle handle authenticated users
        # Use IP as the cache key for anonymous users
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        ip = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "anon")
        return self.cache_format % {"scope": self.scope, "ident": ip}

    def allow_request(self, request, view):
        # Anonymous users are never allowed to upload
        if not request.user or not request.user.is_authenticated:
            self.wait = lambda: None
            return False
        return True   # authenticated — skip this throttle


class UserUploadThrottle(SimpleRateThrottle):
    """
    Authenticated users: limited uploads per hour.
    Rate is set by scope in DEFAULT_THROTTLE_RATES.
    Subclassed per resource so rates can differ.
    """
    scope = "user_upload"

    def get_cache_key(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return None   # AnonUploadThrottle handles anonymous
        return self.cache_format % {
            "scope": self.scope,
            "ident": request.user.pk,
        }


class RigUploadThrottle(UserUploadThrottle):
    """8 rig uploads per hour — Blender is CPU-heavy."""
    scope = "rig_upload"


class AnimationUploadThrottle(UserUploadThrottle):
    """10 animation uploads per hour — file storage limit."""
    scope = "animation_upload"


# ── Read throttles ─────────────────────────────────────────────────────────────

class RigListThrottle(SimpleRateThrottle):
    """GET /rigs/ — scoped rate for listing rigs."""
    scope = "rig_list"

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = request.user.pk
        else:
            forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
            ident = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "anon")
        return self.cache_format % {"scope": self.scope, "ident": ident}


class AnimationListThrottle(SimpleRateThrottle):
    """GET /animations/ — scoped rate for browsing animation library."""
    scope = "animation_list"

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = request.user.pk
        else:
            forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
            ident = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "anon")
        return self.cache_format % {"scope": self.scope, "ident": ident}
"""

Import from here in any view:
    from apps.throttles import AnonUploadThrottle, UserUploadThrottle, ...
"""
from rest_framework.throttling import SimpleRateThrottle, UserRateThrottle, AnonRateThrottle


# ── Upload throttles (heavy operations) ───────────────────────────────────────

class AnonUploadThrottle(SimpleRateThrottle):

    scope = "anon_upload"

    def get_cache_key(self, request, view):
        # Always throttle anon users trying to upload
        if request.user and request.user.is_authenticated:
            return None   # let UserUploadThrottle handle authenticated users
        # Use IP as the cache key for anonymous users
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        ip = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "anon")
        return self.cache_format % {"scope": self.scope, "ident": ip}

    def allow_request(self, request, view):
        # Anonymous users are never allowed to upload
        if not request.user or not request.user.is_authenticated:
            self.wait = lambda: None
            return False
        return True   # authenticated — skip this throttle


class UserUploadThrottle(SimpleRateThrottle):
    """
    Authenticated users: limited uploads per hour.
    Rate is set by scope in DEFAULT_THROTTLE_RATES.
    Subclassed per resource so rates can differ.
    """
    scope = "user_upload"

    def get_cache_key(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return None   # AnonUploadThrottle handles anonymous
        return self.cache_format % {
            "scope": self.scope,
            "ident": request.user.pk,
        }


class RigUploadThrottle(UserUploadThrottle):
    """8 rig uploads per hour — Blender is CPU-heavy."""
    scope = "rig_upload"


class AnimationUploadThrottle(UserUploadThrottle):
    """10 animation uploads per hour — file storage limit."""
    scope = "animation_upload"


# ── Read throttles ─────────────────────────────────────────────────────────────

class RigListThrottle(SimpleRateThrottle):
    """GET /rigs/ — scoped rate for listing rigs."""
    scope = "rig_list"

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = request.user.pk
        else:
            forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
            ident = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "anon")
        return self.cache_format % {"scope": self.scope, "ident": ident}


class AnimationListThrottle(SimpleRateThrottle):
    """GET /animations/ — scoped rate for browsing animation library."""
    scope = "animation_list"

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = request.user.pk
        else:
            forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
            ident = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "anon")
        return self.cache_format % {"scope": self.scope, "ident": ident}