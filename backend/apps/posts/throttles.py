"""
🔹 3. Custom Throttling კლასები
"""
from rest_framework.throttling import SimpleRateThrottle


class PostBurstThrottle(SimpleRateThrottle):
    """
    Custom throttle: ავტ. მომხმარებელს შეუძლია მხოლოდ 1 POST
    request-ის გაგზავნა 10 წამში.

    გამოიყენება posts/create/ endpoint-ზე AnonRateThrottle-სა და
    posts_create scoped throttle-თან ერთად — ყველაზე მკაცრი
    წესი იმარჯვებს.
    """
    scope = "post_burst"   # შეესაბამება DEFAULT_THROTTLE_RATES["post_burst"]

    def get_cache_key(self, request, view):
        # ანონიმურზე არ ვრთავთ — მხოლოდ ავტ. მომხმარებელზე
        if not request.user or not request.user.is_authenticated:
            return None
        return self.cache_format % {
            "scope": self.scope,
            "ident": request.user.pk,
        }


class StrictIPThrottle(SimpleRateThrottle):
    """
    Custom throttle IP-ზე დაყრდნობით:
    ერთი IP-დან მაქს 30 request/წუთში (ავტ. + ანონ. ერთად).
    უფრო მკაცრია ვიდრე AnonRateThrottle (5/min) — ერთმანეთს
    ავსებენ.
    """
    scope = "anon"   # იყენებს "anon" rate-ს (5/min) ამ კლასში
                     # მაგრამ cache key IP-ზეა — არა session-ზე

    def get_cache_key(self, request, view):
        # IP-ის ამოღება (proxy-ების მხარდაჭერით)
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
        else:
            ip = request.META.get("REMOTE_ADDR", "unknown")

        return self.cache_format % {
            "scope": "strict_ip",
            "ident": ip,
        }