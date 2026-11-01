import { memo, useEffect, useRef } from "react";
import { formatTime, weatherText } from "../lib/format";
import { riskColor, riskLabel } from "../lib/risk";
import type { Checkpoint, RouteOption } from "../types";

interface Props {
  route: RouteOption;
  focusIndex: number | null;
  onFocus: (cp: Checkpoint) => void;
}

function CheckpointTable({ route, focusIndex, onFocus }: Props) {
  const focusedRow = useRef<HTMLTableRowElement>(null);
  useEffect(() => {
    focusedRow.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [focusIndex]);

  return (
    <div className="cp-table-wrap">
      <table className="cp-table">
        <thead>
          <tr>
            <th>Mile</th>
            <th>ETA</th>
            <th>Wind</th>
            <th>Rain</th>
            <th>Snow</th>
            <th>Risk</th>
          </tr>
        </thead>
        <tbody>
          {route.checkpoints.map((cp) => {
            const w = cp.weather;
            const focused = cp.index === focusIndex;
            return (
              <tr
                key={cp.index}
                ref={focused ? focusedRow : undefined}
                className={focused ? "focused" : ""}
                onClick={() => onFocus(cp)}
                title={[weatherText(w.weather_code), `${Math.round(w.temp_f)}°F`, ...cp.reasons].join(" · ")}
              >
                <td>{Math.round(cp.mile)}</td>
                <td>{formatTime(cp.eta)}</td>
                <td className={cp.risk.wind ? "hot" : ""}>
                  {w.wind_mph.toFixed(0)}
                  <small> g{w.gust_mph.toFixed(0)}</small>
                </td>
                <td className={cp.risk.rain ? "hot" : ""}>{w.rain_in_hr.toFixed(2)}</td>
                <td className={cp.risk.snow ? "hot" : ""}>{w.snow_in_hr.toFixed(2)}</td>
                <td>
                  <span className="risk-chip" style={{ background: riskColor(cp.risk.level) }}>
                    {riskLabel(cp.risk.level)}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default memo(CheckpointTable);
