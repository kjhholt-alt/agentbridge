// AgentInputDriver -- registry-driven input injection for Unity.
//
// Games register actions at startup via RegisterDefaultActions() or
// BindAction(name, inputAction, kind). The bridge calls
// ApplyCommand(name, value) on every "action" message from the agent.

using System.Collections.Generic;
using UnityEngine;

namespace AgentBridge
{
    public enum ActionKind { Sticky, OneShot, LookDelta }

    public class ActionEntry
    {
        public string InputAction;
        public ActionKind Kind;
    }

    /// <summary>
    /// AgentInputDriver -- holds the action registry and stamps inputs
    /// onto the player. Subclass and override DriveSticky/DriveOneShot/
    /// DriveLookDelta to integrate with the new InputSystem or legacy
    /// Input depending on the project.
    /// </summary>
    public class AgentInputDriver : MonoBehaviour
    {
        public Transform Player;
        protected Dictionary<string, ActionEntry> Registry = new Dictionary<string, ActionEntry>();
        protected Dictionary<string, bool> StickyState = new Dictionary<string, bool>();
        public float PendingYaw;
        public float PendingPitch;
        public float PendingRoll;

        public virtual void RegisterDefaultActions()
        {
            string[] sticky = {"move_forward","move_back","strafe_left","strafe_right",
                                "sprint","crouch_held","block"};
            string[] oneshot = {"attack","interact","vault","crouch_toggle","pause",
                                 "weapon_1","weapon_2","weapon_3","weapon_4"};
            string[] look = {"look_yaw_delta","look_pitch_delta","look_roll_delta"};
            foreach (var n in sticky) Registry[n] = new ActionEntry {InputAction=n, Kind=ActionKind.Sticky};
            foreach (var n in oneshot) Registry[n] = new ActionEntry {InputAction=n, Kind=ActionKind.OneShot};
            foreach (var n in look)    Registry[n] = new ActionEntry {InputAction="",  Kind=ActionKind.LookDelta};
        }

        public Dictionary<string, object> BindAction(string name, string inputAction, string kind)
        {
            if (!IsValidName(name))
                return new Dictionary<string, object> {{"ok", false}, {"error", "invalid action name"}, {"code", 2000}};
            ActionKind k;
            switch (kind) {
                case "sticky": k = ActionKind.Sticky; break;
                case "oneshot": k = ActionKind.OneShot; break;
                case "look_delta": k = ActionKind.LookDelta; break;
                default:
                    return new Dictionary<string, object> {{"ok", false}, {"error", "invalid kind"}, {"code", 2000}};
            }
            Registry[name] = new ActionEntry {InputAction=inputAction, Kind=k};
            return new Dictionary<string, object> {{"ok", true}};
        }

        public Dictionary<string, object> ApplyCommand(string name, object value)
        {
            if (!Registry.TryGetValue(name, out var entry))
                return new Dictionary<string, object> {{"ok", false}, {"error", $"unknown_action: {name}"}, {"code", 2001}};
            switch (entry.Kind)
            {
                case ActionKind.LookDelta:
                    float v = ToFloat(value);
                    if (name.StartsWith("look_yaw")) PendingYaw += v;
                    else if (name.StartsWith("look_pitch")) PendingPitch += v;
                    else if (name.StartsWith("look_roll")) PendingRoll += v;
                    return new Dictionary<string, object> {{"ok", true}};
                case ActionKind.Sticky:
                {
                    bool on = ToBool(value);
                    bool was = StickyState.TryGetValue(name, out var prev) && prev;
                    if (on == was) return new Dictionary<string, object> {{"ok", true}, {"noop", true}};
                    StickyState[name] = on;
                    DriveSticky(entry.InputAction, on);
                    return new Dictionary<string, object> {{"ok", true}};
                }
                case ActionKind.OneShot:
                    DriveOneShot(entry.InputAction);
                    return new Dictionary<string, object> {{"ok", true}};
            }
            return new Dictionary<string, object> {{"ok", false}, {"error", "internal"}, {"code", 3000}};
        }

        public void ReleaseAll()
        {
            foreach (var kv in StickyState)
            {
                if (kv.Value && Registry.TryGetValue(kv.Key, out var entry))
                    DriveSticky(entry.InputAction, false);
            }
            StickyState.Clear();
        }

        // ---- Override hooks for game-specific input integration ----

        protected virtual void DriveSticky(string inputAction, bool on)
        {
            // Default no-op. Games override to call InputSystem.action.Press()/Release()
            // or legacy Input.SetButton() helpers.
        }

        protected virtual void DriveOneShot(string inputAction)
        {
            // Default no-op. Games override to send a one-frame press.
        }

        protected virtual void Update()
        {
            if (PendingYaw == 0f && PendingPitch == 0f && PendingRoll == 0f) return;
            if (Player != null)
            {
                Player.Rotate(0f, -PendingYaw * Mathf.Rad2Deg, 0f, Space.Self);
                Player.Rotate(-PendingPitch * Mathf.Rad2Deg, 0f, 0f, Space.Self);
            }
            PendingYaw = 0f;
            PendingPitch = 0f;
            PendingRoll = 0f;
        }

        private static bool IsValidName(string name)
        {
            if (string.IsNullOrEmpty(name) || name.Length > 48) return false;
            if (name[0] == '_') return false;
            if (!(name[0] >= 'a' && name[0] <= 'z')) return false;
            for (int i = 0; i < name.Length; i++)
            {
                char c = name[i];
                bool ok = (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_';
                if (!ok) return false;
            }
            return true;
        }

        private static bool ToBool(object o)
        {
            if (o is bool b) return b;
            if (o is string s) return s == "true" || s == "1";
            return o != null;
        }

        private static float ToFloat(object o)
        {
            if (o is float f) return f;
            if (o is double d) return (float)d;
            if (o is int i) return i;
            if (o is string s) return float.TryParse(s, out var fv) ? fv : 0f;
            return 0f;
        }
    }
}
