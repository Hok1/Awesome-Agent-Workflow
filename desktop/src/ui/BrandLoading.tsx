import { useState } from "react";
import logo from "../assets/aaw-logo.png";
import "./StartupGate.css";

const greetings = [
  "很高兴见到你，一起把想法变成现实吧。",
  "你好呀，今天也一起做点有意思的事。",
  "欢迎回来，我们慢慢来，一步一步做好。",
  "新的灵感，值得一个好的开始。",
  "伸个懒腰，接下来我们一起搞定。",
  "带上你的好点子，我们一起试试看。",
];

/** Shared brand animation; presentation only, never controls connection timing. */
export function BrandLoading({
  caption,
  hint,
  compact = false,
  immersive = false,
}: {
  readonly caption: string;
  readonly hint?: string;
  readonly compact?: boolean;
  readonly immersive?: boolean;
}) {
  // Pick once per loading screen; replay updates must not shuffle the greeting.
  const [greeting] = useState(
    () => greetings[Math.floor(Math.random() * greetings.length)]!,
  );
  const Heading = compact || immersive ? "h2" : "h1";
  return (
    <div
      className={`startup-brand${immersive ? " startup-brand--immersive" : compact ? " startup-brand--compact" : ""}`}
      role="status"
      aria-live="polite"
    >
      <div className="startup-mark" aria-hidden="true">
        <div className="startup-halo" />
        <img className="startup-logo" src={logo} alt="" draggable={false} />
      </div>
      <Heading className="startup-name">
        Awesome Agent <span>Workspace</span>
      </Heading>
      <p className="startup-hint">{hint ?? greeting}</p>
      <p className="startup-caption">{caption}</p>
    </div>
  );
}
