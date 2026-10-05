# Desktop Pet Experience

The user-facing desktop-pet experience shared by settings, menus, overlays, and
their platform-specific presentations.

## Language

**Shared UX Contract**:
The cross-platform agreement for information architecture, state semantics,
interaction meaning, spacing roles, and brand roles. Platform presentation may
vary without changing this contract.
_Avoid_: Pixel parity, identical native chrome

**Settings System**:
Detailed pet, bubble, collision and work-link preferences. Every preference has
one owner: the tray owns visibility, mouse passthrough and autostart; the pet
menu owns size, playback speed, topmost, roaming and drag-physics shortcuts.
Settings do not duplicate these controls (exit may appear on both menus).
_Avoid_: Modern settings, legacy settings

**Menu Action Model**:
The shared set of menu commands, canonical labels/icons, callbacks, capability
availability, and runtime enablement semantics, independent of platform
presentation.
_Avoid_: Modern menu behavior, legacy menu behavior

**Menu Layout Tree**:
A bundled fixed tree of action IDs and one-level submenus in
`pet/menu_templates/modern-default-v1.json`. Capability checks omit unavailable
actions. User layout editing, alternate templates and Easter-egg entries were
removed on 2026-10-04. The greeting header ("请点击") invokes the pet's
response animation and a random bundled cartoon image bubble, avoiding an
immediate repeat. Important work reminders keep priority.
Behavior repetition uses built-in thresholds, and Todo reminders are retired.
The tray and all pet menu items reuse the historical modern appearance and
visible checked-state layer. Windows tray Context activation opens the owned
Qt menu so its stylesheet and check layer appear. Autostart clicks invert the
current OS state and keep QAction change notifications enabled. The tray's
stable icon/name is 鲸鱼娘.
_Avoid_: Serialized QAction, platform-specific menu order

**Menu Presentation Override**:
Retired on 2026-10-04. Menu commands use canonical labels and semantic icons.
_Avoid_: Renamed command, embedded image bytes

**Capability Unavailable**:
An action cannot exist on the current platform or build; the runtime omits it.
_Avoid_: Disabled feature, hidden action

**Runtime Disabled**:
An action exists on the current platform but its owning feature is currently
off or has no configured content. It keeps its Menu Layout Tree position and is
rendered with a disabled style and explanation; changing the feature toggle
never rewrites or filters the tree.
_Avoid_: Capability unavailable, user-hidden

**Dock Recovery Menu**:
The native macOS Dock context menu that keeps core recovery actions, especially
opening the Settings System, reachable when the pet window is hidden or mouse
input passes through it.
_Avoid_: Pet context menu, tray menu

**Settings Popup Surface**:
The shared settings-menu presentation used by selectors and command buttons.
It owns popup anchoring, minimum trigger width, row geometry, disabled state,
submenu arrows, and trailing selection checks; callers only provide actions.
_Avoid_: Copied menu stylesheet, native button menu indicator

**Image Directory Preview**:
An on-demand right-side drawer for image-directory settings. It uses three
shortest-height columns, preserves each thumbnail's useful aspect ratio, labels
every card with an elided filename and full-name tooltip, and defers directory
scanning and image decoding until the user presses Preview.
_Avoid_: Inline settings grid, eager gallery

**Settings Capability Domain**:
A stable sidebar destination organized by user intent. Every persistent setting
has one owning domain; platform support changes availability, not ownership.
_Avoid_: Module page, Windows settings page

**Report Gate**:
The single control for how much of one aggregated event class the pet reports.
It is a pass probability in `0.00–1.00` (`0.00` silences the class, `1.00`
reports every occurrence) and there is no boolean switch: the settings slider is
the only fine-grained control, while the pet menu offers only the two endpoints.
A gate governs the bubble step alone — detectors and the raw-record chain are
never sampled — and it never covers the whole feature.
_Avoid_: Notification toggle, report percentage, global mute

**Gate Group**:
The collapsible settings block that collects every report gate with the
bubble-phrase rows of its own event class, so a gate sits next to what it
controls. It is expanded by default and auto-expands when a search matches a row
inside it.
_Avoid_: Hidden advanced panel, per-feature switch list

**Session-End Spawn Freeze**:
The process-wide latch armed when the operating system announces that the
session is ending (`WM_QUERYENDSESSION`/`WM_ENDSESSION`, or Qt's session
signals as a fallback). While armed, no child ffmpeg process may be spawned and
existing readers are stopped, because a process created inside a tearing-down
Windows session fails DLL initialization (0xc0000142) and blocks shutdown.
The freeze is one-way: a process that survives a cancelled shutdown stays
frozen rather than resuming animation.
_Avoid_: Shutdown option, ffmpeg kill switch
