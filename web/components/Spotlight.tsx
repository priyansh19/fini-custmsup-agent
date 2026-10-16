import { RefObject, useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import s from '../styles/Spotlight.module.css';

type Props = {
  target: RefObject<HTMLElement>;
  title: string;
  body: string;
  primary: string;          // e.g. "Try brief mode"
  onPrimary: () => void;
  onClose: () => void;
};

const PAD = 8;

/** Spotlight onboarding: dims the page, cuts a hole around `target`, anchors an accessible tooltip to it.
 *  Esc / click outside / "Got it" close it; focus is trapped inside and restored to the target on close. */
export default function Spotlight({ target, title, body, primary, onPrimary, onClose }: Props) {
  const [rect, setRect] = useState<DOMRect | null>(null);
  const [vw, setVw] = useState(1200);
  const card = useRef<HTMLDivElement>(null);
  const primaryBtn = useRef<HTMLButtonElement>(null);

  const measure = useCallback(() => {
    const el = target.current;
    if (el) { setRect(el.getBoundingClientRect()); setVw(window.innerWidth); }
  }, [target]);

  useLayoutEffect(() => {
    target.current?.scrollIntoView({ block: 'nearest' });
    measure();
    window.addEventListener('resize', measure);
    window.addEventListener('scroll', measure, true);
    return () => { window.removeEventListener('resize', measure); window.removeEventListener('scroll', measure, true); };
  }, [measure, target]);

  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    const t = setTimeout(() => primaryBtn.current?.focus(), 30);
    return () => { clearTimeout(t); (target.current || prev)?.focus?.(); };
  }, [target]);

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') { e.preventDefault(); onClose(); return; }
    if (e.key !== 'Tab' || !card.current) return;
    const f = Array.from(card.current.querySelectorAll<HTMLElement>('button'));
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  };

  if (!rect) return null;
  const hole = { top: rect.top - PAD, left: rect.left - PAD, width: rect.width + PAD * 2, height: rect.height + PAD * 2 };
  const mobile = vw < 560;
  const cardW = mobile ? vw - 24 : 340;
  const left = mobile ? 12 : Math.min(Math.max(12, rect.right - cardW + PAD), vw - cardW - 12);
  const arrowLeft = Math.min(Math.max(18, rect.left + rect.width / 2 - left - 8), cardW - 34);

  return (
    <div className={s.root} onKeyDown={onKey}>
      <div className={s.catcher} onMouseDown={onClose} aria-hidden />
      <div className={s.hole} style={hole} aria-hidden />
      <div ref={card} className={s.card} role="dialog" aria-modal="true" aria-labelledby="spot-title" aria-describedby="spot-body"
        style={{ top: hole.top + hole.height + 14, left, width: cardW }}>
        <span className={s.arrow} style={{ left: arrowLeft }} aria-hidden />
        <div className={s.kicker}>New here?</div>
        <h2 id="spot-title">{title}</h2>
        <p id="spot-body">{body}</p>
        <div className={s.actions}>
          <button className={s.ghost} onClick={onClose}>Got it</button>
          <button ref={primaryBtn} className={s.primary} onClick={() => { onPrimary(); onClose(); }}>{primary}</button>
        </div>
      </div>
    </div>
  );
}
