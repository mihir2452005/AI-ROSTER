"use client";

import type React from "react";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  paymentsApi,
  subscriptionsApi,
  authApi,
  emitAuthRefresh,
  getAccessToken,
  type Plan,
  type User,
} from "../../lib/auth-api";

declare global {
  interface Window {
    // Razorpay's checkout script adds this global
    Razorpay: any;
  }
}

// Maps a `plan.features` dict (from the backend) into a list of <li>.
// Supports a small DSL so plans can be customised without frontend code:
//   { items: ["âœ… Unlimited messages", "âŒ Custom personality", ...] }
//   { highlighted: "MOST POPULAR", items: [...] }
//   { items: ["...", { text: "Build your own", cta: "Configure" }] }
function renderPlanFeatures(plan: Plan): React.ReactNode {
  const f = (plan.features ?? {}) as { items?: Array<string | { text: string }> };
  const items = Array.isArray(f.items) ? f.items : [];
  if (items.length === 0) {
    // Fallback when the backend didn't ship a feature list (e.g. dev
    // seed). The legacy hardcoded lists so a missing entry doesn't
    // render an empty plan card.
    return FALLBACK_FEATURES[plan.plan_code]?.map((s, i) => <li key={i}>{s}</li>) ?? null;
  }
  return items.map((it, i) => {
    if (typeof it === "string") return <li key={i}>{it}</li>;
    return <li key={i}>{it.text}</li>;
  });
}

const FALLBACK_FEATURES: Record<string, string[]> = {
  starter: [
    "âœ… Unlimited messages",
    "âœ… Male & female roaster",
    "âœ… Chat history",
    "âŒ Custom personality",
  ],
  pro: [
    "âœ… Everything in Starter",
    "âœ… All 3 roaster types",
    "âœ… Priority support",
    "âœ… Weekly leaderboard rewards",
  ],
  legend: [
    "âœ… Everything in Pro",
    "âœ… Custom personality (build your own)",
    "âœ… 90 days of access",
    "âœ… VIP support & early features",
  ],
};

export default function PricingPage() {
  const router = useRouter();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [checkoutLoading, setCheckoutLoading] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    // Plans are public â€” anyone can view pricing. We only need a
    // logged-in user to subscribe; if the user clicks "Get Pro" while
    // not logged in, we send them to /login and bring them back here
    // after auth.
    Promise.all([paymentsApi.listPlans(), getAccessToken() ? authApi.me() : Promise.resolve(null)])
      .then(([p, u]) => {
        setPlans(p.plans);
        setUser(u);
      })
      .catch((e) => {
        if (e?.status === 401) router.push("/login");
        else setError(e?.detail || "Failed to load plans");
      })
      .finally(() => setLoading(false));
  }, [router]);

  function loadRazorpayScript(): Promise<boolean> {
    return new Promise((resolve) => {
      if (window.Razorpay) {
        resolve(true);
        return;
      }
      const script = document.createElement("script");
      script.src = "https://checkout.razorpay.com/v1/checkout.js";
      script.onload = () => resolve(true);
      script.onerror = () => resolve(false);
      document.body.appendChild(script);
    });
  }

  async function handleSubscribe(plan: Plan) {
    // Anonymous users can't subscribe. Send them to /login and bring
    // them back here after auth.
    if (!getAccessToken()) {
      router.push("/login?return=/pricing");
      return;
    }
    if (plan.plan_code === "starter" && !confirm(
      "Starter plan is for trying things out. Most users pick Pro for the best value. Continue?"
    )) {
      return;
    }
    setError("");
    setCheckoutLoading(plan.plan_code);
    try {
      const scriptLoaded = await loadRazorpayScript();
      if (!scriptLoaded) {
        setError("Failed to load payment SDK. Check your internet connection.");
        return;
      }
      const order = await paymentsApi.createOrder(plan.plan_code);

      const options = {
        key: order.key_id,
        amount: order.amount,
        currency: order.currency,
        name: "RoastGPT",
        description: order.plan_name,
        order_id: order.order_id,
        handler: async (response: {
          razorpay_order_id: string;
          razorpay_payment_id: string;
          razorpay_signature: string;
        }) => {
          // The Razorpay modal has closed and the user has paid.
          // Verify on our backend. Note: clearing checkoutLoading is
          // handled by ondismiss â€” we only clear it here on error so
          // the user can retry without the button being stuck.
          try {
            const r = await paymentsApi.verifyPayment(response);
            // Surface the actual server message â€” "Payment verified and
            // subscription activated" on first run, "Payment already
            // verified" on idempotent retry. Both are fine.
            const alreadyVerified = /already/i.test(r.message);
            alert(
              alreadyVerified
                ? "You've already activated " + plan.name + " â€” no action needed."
                : "ðŸŽ‰ " + r.message + "! Welcome to " + plan.name + "."
            );
            const u = await authApi.me();
            setUser(u);
            // Tell the HeaderAuth in the root layout to refetch so the
            // "â­ Subscribe" badge disappears without a full reload.
            emitAuthRefresh();
            router.push("/account");
          } catch (e: any) {
            setError("Payment verification failed: " + (e?.detail || "unknown"));
            setCheckoutLoading(null);
          }
        },
        prefill: {
          email: user?.email || "",
          name: user?.full_name || "",
        },
        theme: { color: "#7c3aed" },
        modal: {
          ondismiss: () => setCheckoutLoading(null),
        },
      };
      const rzp = new window.Razorpay(options);
      rzp.open();
    } catch (e: any) {
      setError(e?.detail || "Checkout failed");
      setCheckoutLoading(null);
    }
  }

  if (loading) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <p className="text-slate-500">Loading plansâ€¦</p>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-900 to-slate-700 px-4 py-12">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-12">
          <h1 className="text-4xl font-bold text-white mb-3">Choose your roast</h1>
          <p className="text-slate-300">
            All plans include unlimited messages, no ads, and full safety filters.
          </p>
          {user?.has_active_subscription && (
            <p className="mt-3 text-emerald-300 text-sm">
              âœ… You have an active subscription. Manage it in <a href="/account" className="underline">Account</a>.
            </p>
          )}
        </div>

        {error && (
          <div className="mb-6 p-4 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm max-w-2xl mx-auto">
            {error}
          </div>
        )}

        <div className="grid md:grid-cols-3 gap-6">
          {plans.map((plan) => {
            const isPro = plan.plan_code === "pro";
            // `plan.features.highlighted` lets the backend mark a plan
            // as the "most popular" without the frontend hardcoding it.
            const f = (plan.features ?? {}) as { highlighted?: string };
            const highlightLabel = f.highlighted;
            return (
              <div
                key={plan.plan_code}
                className={`bg-white rounded-2xl p-8 shadow-xl ${
                  isPro || highlightLabel ? "ring-2 ring-purple-500 scale-105" : ""
                }`}
              >
                {(isPro || highlightLabel) && (
                  <span className="inline-block mb-3 px-3 py-1 text-xs font-bold rounded-full bg-purple-100 text-purple-700">
                    {highlightLabel ?? "MOST POPULAR"}
                  </span>
                )}
                <h2 className="text-2xl font-bold text-slate-900">{plan.name}</h2>
                <p className="text-slate-500 text-sm mt-1">
                  {plan.duration_days} days
                </p>
                <div className="mt-4 mb-6">
                  <span className="text-4xl font-bold text-slate-900">{plan.price_display}</span>
                  <span className="text-slate-500 text-sm"> / {plan.duration_days} days</span>
                </div>
                <ul className="space-y-2 text-sm text-slate-600 mb-8 min-h-[140px]">
                  {renderPlanFeatures(plan)}
                </ul>
                <button
                  onClick={() => handleSubscribe(plan)}
                  disabled={checkoutLoading === plan.plan_code || user?.has_active_subscription}
                  className={`w-full py-3 font-semibold rounded-lg transition ${
                    isPro
                      ? "bg-gradient-to-r from-purple-600 to-pink-600 text-white hover:opacity-90"
                      : "bg-slate-900 text-white hover:bg-slate-800"
                  } disabled:opacity-50`}
                >
                  {checkoutLoading === plan.plan_code
                    ? "Opening checkoutâ€¦"
                    : user?.has_active_subscription
                    ? "Already subscribed"
                    : `Get ${plan.name}`}
                </button>
              </div>
            );
          })}
        </div>

        <p className="text-center text-slate-400 text-xs mt-8">
          Payments secured by Razorpay. Cancel anytime from your account page.
        </p>
      </div>
    </main>
  );
}
