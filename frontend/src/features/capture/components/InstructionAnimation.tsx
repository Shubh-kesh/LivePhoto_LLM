/**
 * Preparation instruction animation (M5.5 §5-8, §58, §94).
 *
 * A lightweight, original, non-photorealistic SVG illustration animated with pure CSS. It cycles:
 *   1. mask fades in then away
 *   2. spectacles fade in then away
 *   3. the face slides into the guide and a check appears
 * Under prefers-reduced-motion the illustration degrades to the clear final state (face centered,
 * mask and spectacles gone, check visible). The static instruction list always carries the content,
 * so no animation is required to understand the guidance.
 */

export function InstructionAnimation() {
  return (
    <div
      className="lp-anim"
      role="img"
      aria-label="Illustration: remove your mask, remove your spectacles, then keep your face centered and clearly visible"
    >
      <svg
        className="lp-anim__svg"
        viewBox="0 0 200 220"
        width="200"
        height="220"
        aria-hidden="true"
      >
        <g className="lp-anim__scene">
          {/* Face guide oval */}
          <ellipse className="lp-anim__guide" cx="100" cy="105" rx="62" ry="80" />
          {/* Head + features */}
          <g className="lp-anim__face">
            <circle className="lp-anim__head" cx="100" cy="100" r="42" />
            <circle className="lp-anim__eye" cx="85" cy="92" r="3.4" />
            <circle className="lp-anim__eye" cx="115" cy="92" r="3.4" />
            <path className="lp-anim__mouth" d="M88 118 q12 10 24 0" />
          </g>
          {/* Mask covering the lower face */}
          <g className="lp-anim__mask">
            <path d="M58 108 q42 -22 84 0 q6 26 -42 34 q-48 -8 -42 -34Z" />
            <path className="lp-anim__mask__fold" d="M58 116 h84" />
          </g>
          {/* Spectacles */}
          <g className="lp-anim__glasses">
            <circle cx="85" cy="92" r="12" />
            <circle cx="115" cy="92" r="12" />
            <path d="M97 92 h6" />
          </g>
          {/* Final confirmation check */}
          <g className="lp-anim__check">
            <circle cx="160" cy="40" r="14" />
            <path d="M154 40 l4.5 4.5 8 -8.5" />
          </g>
        </g>
      </svg>
    </div>
  )
}
