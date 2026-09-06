/** Small original local SVG icon set (M5.5 §49, §91). No third-party icon library, no remote assets. */

import type { SVGProps } from 'react'

function base(props: SVGProps<SVGSVGElement>) {
  return {
    width: 24,
    height: 24,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.8,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
    ...props,
  }
}

export function IconCamera(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base(props)}>
      <path d="M4 7h3l2-3h6l2 3h3a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1Z" />
      <circle cx="12" cy="13" r="3.2" />
    </svg>
  )
}

export function IconSwitchCamera(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base(props)}>
      <path d="M9 3 6 6l3 3" />
      <path d="M6 6h9a4 4 0 0 1 4 4" />
      <path d="M15 21l3-3-3-3" />
      <path d="M18 18H9a4 4 0 0 1-4-4" />
    </svg>
  )
}

export function IconMask(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base(props)}>
      <path d="M4 12c1-4 3-7 8-7s7 3 8 7c-1 4-3 7-8 7s-7-3-8-7Z" />
      <path d="M4 10h16" />
      <path d="M4 14h16" />
      <circle cx="9" cy="12" r="0.6" fill="currentColor" />
      <circle cx="15" cy="12" r="0.6" fill="currentColor" />
    </svg>
  )
}

export function IconGlasses(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base(props)}>
      <circle cx="7" cy="14" r="2.6" />
      <circle cx="17" cy="14" r="2.6" />
      <path d="M9.6 13.6 6 7.5" />
      <path d="M14.4 13.6 18 7.5" />
      <path d="M12 13v1" />
    </svg>
  )
}

export function IconLight(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base(props)}>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 3v2" />
      <path d="M12 19v2" />
      <path d="M4.5 4.5l1.4 1.4" />
      <path d="M18.1 18.1l1.4 1.4" />
      <path d="M3 12h2" />
      <path d="M19 12h2" />
      <path d="M4.5 19.5l1.4-1.4" />
      <path d="M18.1 5.9l1.4-1.4" />
    </svg>
  )
}

export function IconCheck(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base(props)}>
      <path d="M5 12.5 10 17.5 19 7" />
    </svg>
  )
}

export function IconWarning(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base(props)}>
      <path d="M10.3 4.1 2.8 17.4a1.6 1.6 0 0 0 1.4 2.4h15.6a1.6 1.6 0 0 0 1.4-2.4L13.7 4.1a1.6 1.6 0 0 0-3.4 0Z" />
      <path d="M12 9.5v4" />
      <path d="M12 16.4v.1" />
    </svg>
  )
}

export function IconBack(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base(props)}>
      <path d="M15 5l-7 7 7 7" />
    </svg>
  )
}

export function IconHelp(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base(props)}>
      <circle cx="12" cy="12" r="9" />
      <path d="M9.6 9.2a2.5 2.5 0 1 1 3.6 2.2c-.8.4-1.2 1-1.2 1.9" />
      <path d="M12 16.6v.1" />
    </svg>
  )
}
