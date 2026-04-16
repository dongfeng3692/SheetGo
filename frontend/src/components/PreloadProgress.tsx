import type { Component } from "solid-js";
import { formatPreloadLabel } from "../lib/preload-display";

interface Props {
  fileName?: string;
  progress?: number;
  stage?: string;
  message?: string;
}

const PreloadProgress: Component<Props> = (props) => {
  const progress = () => props.progress ?? 0;
  const stageText = () => formatPreloadLabel(props.stage, props.message);

  return (
    <div class="pointer-events-none fixed bottom-5 right-5 z-40 w-[min(360px,calc(100vw-1.5rem))]" aria-live="polite">
      <div class="surface-card px-4 py-4">
        <div class="flex items-start justify-between gap-3">
          <div>
            <div class="text-xs uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
              正在预加载工作簿
            </div>
            <div class="mt-2 text-sm font-medium text-[var(--text-primary)]">
              {props.fileName ?? "正在准备工作簿"}
            </div>
          </div>
          <div class="subtle-pill accent">{Math.round(progress())}%</div>
        </div>

        <div class="mt-3 text-sm leading-6 text-[var(--text-secondary)]">
          {stageText()}
        </div>

        <div class="mt-4 h-2 overflow-hidden rounded-full bg-[var(--bg-muted)]">
          <div
            class="h-full rounded-full bg-[var(--accent-strong)] transition-all duration-300"
            style={{ width: `${progress()}%` }}
          />
        </div>
      </div>
    </div>
  );
};

export default PreloadProgress;
