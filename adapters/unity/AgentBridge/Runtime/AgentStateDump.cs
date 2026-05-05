// AgentStateDump -- Unity port of the base state-dump.
//
// Returns the minimum-required state per AgentBridge spec v1
// (player, time). Games subclass and override ExtraState() to add
// engine- or game-specific keys.

using System.Collections.Generic;
using UnityEngine;

namespace AgentBridge
{
    public class AgentStateDump : MonoBehaviour
    {
        public Transform Player;

        public virtual Dictionary<string, object> Snapshot()
        {
            var d = new Dictionary<string, object>
            {
                ["player"] = PlayerDump(),
                ["time"]   = TimeDump(),
                ["ticks"]  = Time.frameCount,
            };
            var extra = ExtraState();
            if (extra != null)
            {
                foreach (var kv in extra) d[kv.Key] = kv.Value;
            }
            return d;
        }

        public virtual Dictionary<string, object> ExtraState() { return null; }

        protected virtual Dictionary<string, object> PlayerDump()
        {
            var d = new Dictionary<string, object>();
            if (Player == null)
            {
                var go = GameObject.FindWithTag("Player");
                if (go != null) Player = go.transform;
            }
            if (Player == null)
            {
                d["position"] = new[] {0.0, 0.0, 0.0};
                return d;
            }
            d["position"] = new[]
            {
                Round(Player.position.x),
                Round(Player.position.y),
                Round(Player.position.z),
            };
            d["yaw"] = Round(Player.eulerAngles.y * Mathf.Deg2Rad);
            d["pitch"] = Round(Player.eulerAngles.x * Mathf.Deg2Rad);
            return d;
        }

        protected virtual Dictionary<string, object> TimeDump()
        {
            return new Dictionary<string, object>
            {
                ["session_seconds"] = Round(Time.time),
                ["frame"] = Time.frameCount,
            };
        }

        // Fast 64-bit FNV-1a hash for snapshot determinism checks.
        public string SnapshotHash()
        {
            string canonical = CanonicalJson(Snapshot());
            return Fnv64(canonical);
        }

        private static string CanonicalJson(object o)
        {
            if (o is Dictionary<string, object> d)
            {
                var keys = new List<string>(d.Keys);
                keys.Sort();
                var sb = new System.Text.StringBuilder();
                sb.Append('{');
                bool first = true;
                foreach (var k in keys)
                {
                    if (!first) sb.Append(',');
                    sb.Append('"').Append(k).Append("\":");
                    sb.Append(CanonicalJson(d[k]));
                    first = false;
                }
                sb.Append('}');
                return sb.ToString();
            }
            if (o is double[] arr)
            {
                var sb = new System.Text.StringBuilder();
                sb.Append('[');
                for (int i = 0; i < arr.Length; i++)
                {
                    if (i > 0) sb.Append(',');
                    sb.Append(arr[i].ToString("G17"));
                }
                sb.Append(']');
                return sb.ToString();
            }
            if (o is double dv) return dv.ToString("G17");
            if (o is float fv) return ((double)fv).ToString("G17");
            if (o is int iv) return iv.ToString();
            if (o is bool bv) return bv ? "true" : "false";
            if (o is string sv) return $"\"{sv}\"";
            return "null";
        }

        private static string Fnv64(string s)
        {
            // 0xCBF29CE484222325 in unsigned -> signed 64-bit
            unchecked
            {
                ulong h = 0xCBF29CE484222325UL;
                ulong p = 1099511628211UL;
                var bytes = System.Text.Encoding.UTF8.GetBytes(s);
                for (int i = 0; i < bytes.Length; i++)
                {
                    h ^= bytes[i];
                    h *= p;
                }
                return h.ToString("x16");
            }
        }

        private static double Round(float v) { return Mathf.Round(v * 100f) / 100f; }
    }
}
