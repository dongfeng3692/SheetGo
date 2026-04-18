import type { Component } from "solid-js";

interface LaunchScreenProps {
  closing?: boolean;
}

const LaunchScreen: Component<LaunchScreenProps> = (props) => (
  <div
    class="launch-screen"
    classList={{ closing: props.closing }}
    aria-live="polite"
    aria-label="应用启动中"
  >
    <div class="launch-screen-backdrop" aria-hidden="true" />
    <div class="launch-screen-grid" aria-hidden="true" />
    <div class="launch-screen-radial" aria-hidden="true" />
    <div class="launch-screen-noise" aria-hidden="true" />
    <div class="launch-screen-vignette" aria-hidden="true" />

    <div class="launch-screen-panel">
      <div class="launch-brand-mark" aria-hidden="true">
        <span class="launch-brand-trail left" />
        <span class="launch-brand-trail right" />
        <span class="launch-brand-pulse" />
        <span class="launch-brand-halo" />
        <span class="launch-brand-sheet back" />
        <span class="launch-brand-sheet front" />
        <span class="launch-brand-ring outer" />
        <span class="launch-brand-ring inner" />
        <span class="launch-brand-core">
          <span class="launch-brand-glyph">E</span>
        </span>
        <span class="launch-brand-flare" />
        <span class="launch-brand-comet comet-a" />
        <span class="launch-brand-comet comet-b" />
      </div>

      <div class="launch-copy">
        <div class="launch-kicker">表格助手</div>
        <div class="launch-title-shell">
          <div class="launch-title">SheetGo</div>
        </div>
        <div class="launch-slogan">
          你专业的 <span>Excel</span> 私人管家
        </div>
      </div>
    </div>
  </div>
);

export default LaunchScreen;
