"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  paymentsApi,
  subscriptionsApi,
  authApi,
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

export default function PricingPage() {
  const router = useRouter();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [checkoutLoading, setCheckoutLoading] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const token = getAccessToken();
    if (!token) {
      router.push("/login");
      return;
    }
    Promise.all([paymentsApi.listPlans(), authApi.me()])
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
          try {
            await paymentsApi.verifyPayment(response);
            alert("🎉 Subscription activated! Welcome to " + plan.name + ".");
            const u = await authApi.me();
            setUser(u);
            router.push("/");
          } catch (e: any) {
            setError("Payment verification failed: " + (e?.detail || "unknown"));
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
    } finally {
      setCheckoutLoading(null);
    }
  }

  if (loading) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <p className="text-slate-500">Loading plans…</p>
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
              ✅ You have an active subscription. Manage it in <a href="/account" className="underline">Account</a>.
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
            return (
              <div
                key={plan.plan_code}
                className={`bg-white rounded-2xl p-8 shadow-xl ${
                  isPro ? "ring-2 ring-purple-500 scale-105" : ""
                }`}
              >
                {isPro && (
                  <span className="inline-block mb-3 px-3 py-1 text-xs font-bold rounded-full bg-purple-100 text-purple-700">
                    MOST POPULAR
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
                  {plan.plan_code === "starter" && (
                    <>
                      <li>✅ Unlimited messages</li>
                      <li>✅ Male & female roaster</li>
                      <li>✅ Chat history</li>
                      <li className="text-slate-400">❌ Custom personality</li>
                    </>
                  )}
                  {plan.plan_code === "pro" && (
                    <>
                      <li>✅ Everything in Starter</li>
                      <li>✅ All 3 roaster types</li>
                      <li>✅ Priority support</li>
                      <li>✅ Weekly leaderboard rewards</li>
                    </>
                  )}
                  {plan.plan_code === "legend" && (
                    <>
                      <li>✅ Everything in Pro</li>
                      <li>✅ Custom personality (build your own)</li>
                      <li>✅ 90 days of access</li>
                      <li>✅ VIP support & early features</li>
                    </>
                  )}
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
                    ? "Opening checkout…"
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
