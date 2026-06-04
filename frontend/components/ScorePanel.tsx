"use client";

import { motion } from "framer-motion";
import type { SessionScores } from "@/lib/types";

interface Props {
  scores: SessionScores;
}

export default function ScorePanel({ scores }: Props) {
  const damage = scores.emotional_damage;
  const damageColor =
    damage < 25 ? "from-success to-accent-3"
    : damage < 50 ? "from-accent-3 to-accent-2"
    : damage < 75 ? "from-accent-2 to-accent"
    : "from-accent to-accent-2";

  return (
    <div className="card sticky top-20">
      <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-muted">
        Live roast score
      </h3>

      <div className="mt-4">
        <div className="flex items-baseline justify-between">
          <span className="text-xs text-muted">Confidence Lost</span>
          <span className="font-mono text-sm font-semibold">{scores.confidence_lost}%</span>
        </div>
        <div className="mt-1 h-2 overflow-hidden rounded-full bg-border/60">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${scores.confidence_lost}%` }}
            transition={{ duration: 0.6, ease: "easeOut" }}
            className="h-full rounded-full bg-gradient-to-r from-accent-3 to-accent"
          />
        </div>
      </div>

      <div className="mt-4">
        <div className="flex items-baseline justify-between">
          <span className="text-xs text-muted">Emotional Damage</span>
          <span className="font-mono text-sm font-semibold">{damage}%</span>
        </div>
        <div className="mt-1 h-2 overflow-hidden rounded-full bg-border/60">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${damage}%` }}
            transition={{ duration: 0.6, ease: "easeOut" }}
            className={`h-full rounded-full bg-gradient-to-r ${damageColor}`}
          />
        </div>
      </div>

      <dl className="mt-5 space-y-2 text-sm">
        <Row label="Delusion Level"  value={scores.delusion_level} />
        <Row label="Reality Checks"  value={scores.reality_checks} />
        <Row label="Bad Decisions"   value={scores.questionable_decisions} />
        <Row label="Excuses Used"    value={scores.excuses_used} />
        <Row label="Recovery Time"   value={scores.recovery_time} />
      </dl>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="text-right text-sm font-medium">{value}</dd>
    </div>
  );
}
