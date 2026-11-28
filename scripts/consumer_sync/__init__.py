"""Consumer-sync CLIs that are not delivered to consumers (cohesion round-3 M5).

Maint 68/69/71/82/90 and Health 68/70/72/73/74/83 run these from a Workflows checkout.
The manifest compiler, plan scoping, phase selection and plan-rotation guard stay at the
root of scripts/ because Maint 68 runs them from the immutable source commit it delivers.
"""
