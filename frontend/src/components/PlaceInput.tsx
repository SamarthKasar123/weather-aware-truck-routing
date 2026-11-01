import { useEffect, useId, useRef, useState } from "react";
import { geocode } from "../lib/api";
import type { Place } from "../types";

interface Props {
  label: string;
  value: Place | string;
  onChange: (v: Place | string) => void;
  placeholder?: string;
}

const DEBOUNCE_MS = 250;

/** Text input with place autocomplete. Emits a Place once a suggestion is picked. */
export default function PlaceInput({ label, value, onChange, placeholder }: Props) {
  const id = useId();
  const text = typeof value === "string" ? value : value.label;
  const resolved = typeof value !== "string";
  const [suggestions, setSuggestions] = useState<Place[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const skipNext = useRef(false);

  useEffect(() => {
    if (resolved || skipNext.current || text.trim().length < 3) {
      skipNext.current = false;
      setSuggestions([]);
      return;
    }
    const ctrl = new AbortController();
    const timer = window.setTimeout(() => {
      geocode(text, ctrl.signal)
        .then((r) => {
          setSuggestions(r);
          setActive(-1);
        })
        .catch(() => setSuggestions([]));
    }, DEBOUNCE_MS);
    return () => {
      ctrl.abort();
      window.clearTimeout(timer);
    };
  }, [text, resolved]);

  const pick = (p: Place) => {
    skipNext.current = true;
    onChange(p);
    setOpen(false);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (!open || !suggestions.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => (a + 1) % suggestions.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => (a <= 0 ? suggestions.length - 1 : a - 1));
    } else if (e.key === "Enter" && active >= 0) {
      e.preventDefault();
      pick(suggestions[active]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  return (
    <div className="field place-field">
      <label htmlFor={id}>{label}</label>
      <div className="place-input-wrap">
        <input
          id={id}
          type="text"
          autoComplete="off"
          value={text}
          placeholder={placeholder}
          onChange={(e) => {
            onChange(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => window.setTimeout(() => setOpen(false), 150)}
          onKeyDown={onKeyDown}
          role="combobox"
          aria-expanded={open && suggestions.length > 0}
          aria-controls={`${id}-list`}
          required
        />
        {resolved && <span className="resolved" title="Location confirmed">✓</span>}
      </div>
      {open && suggestions.length > 0 && (
        <ul className="suggestions" id={`${id}-list`} role="listbox">
          {suggestions.map((s, i) => (
            <li
              key={`${s.lat},${s.lon},${i}`}
              role="option"
              aria-selected={i === active}
              className={i === active ? "active" : ""}
              onMouseDown={(e) => {
                e.preventDefault();
                pick(s);
              }}
            >
              {s.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
