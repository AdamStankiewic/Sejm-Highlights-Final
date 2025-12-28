# Streamer Detection UX - Design Document

## Current State Analysis

### Jak to działa TERAZ:

```python
# pipeline/stage_09_youtube.py:532
channel_id = self.config.youtube.channel_id  # Z config.yml
profile = self.streamer_manager.detect_from_youtube(channel_id)

if not profile:
    logger.warning(f"No streamer profile for channel {channel_id}")
    return None  # ❌ Brak profilu = brak AI metadata
```

**Problemy z obecnym podejściem:**

1. ❌ **Brak potwierdzenia** - użytkownik nie wie co zostało wykryte
2. ❌ **Brak fallbacku** - jeśli detekcja się nie uda → brak AI metadata
3. ❌ **Brak możliwości zmiany** - nie można wybrać innego profilu
4. ❌ **Brak dodawania nowych** - nie można utworzyć profilu w locie
5. ❌ **Silent failure** - użytkownik nie wie dlaczego AI nie działa

---

## Proposed UX Flow - Critical Analysis

### Option 1: Dialog Przed Każdym Uploadem ❌

**Flow:**
```
User clicks "Upload to YouTube"
  ↓
System detects streamer from channel_id
  ↓
Dialog: "Wykryto: Sejm. Czy to poprawne? [Tak][Zmień][Dodaj]"
  ↓
If "Tak" → proceed
If "Zmień" → dropdown z listą
If "Dodaj" → dialog tworzenia profilu
```

**Plusy:**
- ✅ Zawsze można zmienić streamera
- ✅ Użytkownik ma kontrolę

**Minusy:**
- ❌ **Bardzo irytujące** - dialog przy KAŻDYM uploadzje
- ❌ Spowalnia workflow dla power users
- ❌ Większość czasu detekcja jest OK i dialog jest zbędny

**Ocena: 3/10** - zbyt inwazyjne

---

### Option 2: Globalne Ustawienie w Settings ❌

**Flow:**
```
User opens Settings → "Streamer Profile" tab
  ↓
Dropdown: [Sejm] [Asmongold] [Pokimane] [+ Add New]
  ↓
System zapamiętuje wybór w config.yml
  ↓
Przy uploadzje zawsze używa tego profilu (bez auto-detekcji)
```

**Plusy:**
- ✅ Nie przeszkadza w workflow
- ✅ Prosty UI

**Minusy:**
- ❌ **Brak auto-detekcji** - użytkownik musi ręcznie ustawić
- ❌ Nie działa dla multi-streamer workflow
- ❌ Co jeśli użytkownik zapomni ustawić?

**Ocena: 5/10** - zbyt sztywne

---

### Option 3: Hybrid (Auto-detect + Potwierdzenie gdy potrzebne) ✅

**Flow:**

#### 3A. Standardowy przypadek (profil znaleziony):
```
User clicks "Upload to YouTube"
  ↓
System detects: profile = sejm ✅
  ↓
Status bar: "🤖 Using profile: Sejm (Kancelaria Sejmu)"
  ↓
Proceed z uploadem (BEZ dialoga)
  ↓
[OPCJA] Przycisk "Change profile" w upload dialog
```

#### 3B. Profil nie znaleziony:
```
User clicks "Upload to YouTube"
  ↓
System detects: profile = None ❌
  ↓
⚠️ DIALOG: "Nie znaleziono profilu dla channel_id: UCxxxx"

Options:
  [📋 Wybierz z listy] [➕ Utwórz nowy] [⏭️ Pomiń (legacy mode)]

If "Wybierz z listy":
  → Dropdown z wszystkimi profilami
  → Checkbox: "Zapamiętaj dla channel_id: UCxxxx"

If "Utwórz nowy":
  → Dialog z formularzem (nazwa, język, platform info)
  → Auto-zapisuje profil do pipeline/streamers/profiles/

If "Pomiń":
  → Upload bez AI metadata (legacy fallback)
```

#### 3C. Manual override (opcjonalnie):
```
Upload Dialog ma dodatkowy panel:

┌─ Streamer Profile ─────────────────┐
│ Auto-detected: Sejm ✓              │
│ [Change] [Edit Profile]            │
└────────────────────────────────────┘

If user clicks "Change":
  → Dropdown z listą + "Add new"
```

**Plusy:**
- ✅ **Nie przeszkadza** gdy wszystko działa (90% przypadków)
- ✅ **Pomaga** gdy potrzebne (profil nie znaleziony)
- ✅ Możliwość manual override dla power users
- ✅ Zachowuje backwards compatibility (legacy mode)
- ✅ Może zapamiętać wybór dla danego channel_id

**Minusy:**
- ⚠️ Więcej kodu do implementacji
- ⚠️ Trzeba dodać UI do app.py

**Ocena: 9/10** - ✅ **RECOMMENDED**

---

## Detailed Design: Option 3 Implementation

### Phase 1: Auto-Detection z Info Bar

**Lokalizacja w GUI:**
- Upload Dialog (tab YouTube Upload)
- Info bar pod przyciskiem "Upload"

**UI Mockup:**
```
┌─ YouTube Upload ────────────────────────────────────────┐
│                                                          │
│  Title:     [Auto-generated from AI                  ]  │
│  Description: [Auto-generated...                     ]  │
│                                                          │
│  ┌─ Streamer Profile ────────────────────────────────┐  │
│  │ 🤖 Auto-detected: Sejm (Kancelaria Sejmu)        │  │
│  │ Language: PL | Platform: YouTube                  │  │
│  │ [Change Profile...]                               │  │
│  └───────────────────────────────────────────────────┘  │
│                                                          │
│  [Upload to YouTube]                                     │
└──────────────────────────────────────────────────────────┘
```

**Kod:**
```python
# app.py - w YouTubeUploadTab
def detect_streamer(self):
    """Detect streamer profile from config"""
    try:
        from pipeline.streamers import get_manager
        manager = get_manager()

        channel_id = self.config.youtube.channel_id
        profile = manager.detect_from_youtube(channel_id)

        if profile:
            # Show info bar
            self.profile_info.setText(
                f"🤖 Auto-detected: {profile.name}\n"
                f"Language: {profile.primary_language.upper()} | "
                f"Platform: {profile.primary_platform.title()}"
            )
            self.profile_info.setStyleSheet("background-color: #e8f5e9; padding: 8px;")
            self.current_profile = profile
        else:
            # Show warning + prompt
            self.profile_info.setText(
                f"⚠️ No profile found for channel: {channel_id}\n"
                f"Click 'Change Profile' to select or create one."
            )
            self.profile_info.setStyleSheet("background-color: #fff3e0; padding: 8px;")
            self.current_profile = None

            # Auto-show dialog if no profile
            self.show_profile_selection_dialog()

    except ImportError:
        # StreamerManager not available - backwards compatibility
        self.profile_info.setText("ℹ️ Legacy mode (no streamer profiles)")
        self.current_profile = None
```

---

### Phase 2: Profile Selection Dialog

**Trigger:**
- Auto-shown gdy profile = None
- Manual: user clicks "Change Profile..."

**UI Mockup:**
```
┌─ Select Streamer Profile ────────────────────────────────┐
│                                                           │
│  Channel ID: UCWd8gHV5Qt-bBa4dI98cS0Q                    │
│                                                           │
│  Select Profile:                                          │
│  ┌─────────────────────────────────────────────────────┐ │
│  │ ○ Sejm (Kancelaria Sejmu)                   [PL]   │ │
│  │ ○ Asmongold                                  [EN]   │ │
│  │ ○ Pokimane                                   [EN]   │ │
│  │ ○ Polski Streamer                            [PL]   │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                           │
│  ☑ Remember for this channel                             │
│                                                           │
│  [➕ Create New Profile]  [⏭️ Skip (Legacy)]  [OK]       │
└───────────────────────────────────────────────────────────┘
```

**Kod:**
```python
class ProfileSelectionDialog(QDialog):
    """Dialog for selecting/creating streamer profile"""

    def __init__(self, parent, channel_id: str, current_profile=None):
        super().__init__(parent)
        self.channel_id = channel_id
        self.selected_profile = current_profile
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Select Streamer Profile")
        layout = QVBoxLayout()

        # Channel ID display
        layout.addWidget(QLabel(f"Channel ID: {self.channel_id}"))

        # Profile list
        self.profile_list = QListWidget()

        from pipeline.streamers import get_manager
        manager = get_manager()

        for profile in manager.list_all():
            item_text = (
                f"{profile.name} "
                f"[{profile.primary_language.upper()}]"
            )
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, profile.streamer_id)
            self.profile_list.addItem(item)

        layout.addWidget(QLabel("Select Profile:"))
        layout.addWidget(self.profile_list)

        # Remember checkbox
        self.remember_checkbox = QCheckBox("Remember for this channel")
        self.remember_checkbox.setChecked(True)
        layout.addWidget(self.remember_checkbox)

        # Buttons
        button_layout = QHBoxLayout()

        create_btn = QPushButton("➕ Create New Profile")
        create_btn.clicked.connect(self.create_new_profile)
        button_layout.addWidget(create_btn)

        skip_btn = QPushButton("⏭️ Skip (Legacy)")
        skip_btn.clicked.connect(self.skip_profile)
        button_layout.addWidget(skip_btn)

        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept_selection)
        ok_btn.setDefault(True)
        button_layout.addWidget(ok_btn)

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def accept_selection(self):
        """User selected a profile"""
        current_item = self.profile_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "No Selection", "Please select a profile")
            return

        streamer_id = current_item.data(Qt.ItemDataRole.UserRole)

        from pipeline.streamers import get_manager
        manager = get_manager()
        self.selected_profile = manager.get(streamer_id)

        # Save mapping if remember is checked
        if self.remember_checkbox.isChecked():
            self.save_channel_mapping(self.channel_id, streamer_id)

        self.accept()

    def create_new_profile(self):
        """Open create profile dialog"""
        dialog = CreateProfileDialog(self, self.channel_id)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Refresh list
            self.profile_list.clear()

            from pipeline.streamers import get_manager
            manager = get_manager()
            manager.reload()

            # Repopulate
            self.init_ui()

    def skip_profile(self):
        """Skip profile selection - use legacy mode"""
        self.selected_profile = None
        self.accept()

    def save_channel_mapping(self, channel_id: str, streamer_id: str):
        """Save channel_id → streamer_id mapping"""
        # Option A: Save to profiles/{streamer}.yaml
        # Add channel_id to platforms.youtube.channel_id

        # Option B: Save to separate mapping file
        mapping_file = Path("config/channel_mappings.yaml")

        if mapping_file.exists():
            with open(mapping_file, 'r') as f:
                mappings = yaml.safe_load(f) or {}
        else:
            mappings = {}

        mappings[channel_id] = streamer_id

        with open(mapping_file, 'w') as f:
            yaml.dump(mappings, f)

        logger.info(f"Saved mapping: {channel_id} → {streamer_id}")
```

---

### Phase 3: Create Profile Dialog

**Trigger:**
- User clicks "Create New Profile" w selection dialog

**UI Mockup:**
```
┌─ Create New Streamer Profile ────────────────────────────┐
│                                                           │
│  Streamer ID*: [sejm_________________]                   │
│                (lowercase, no spaces)                     │
│                                                           │
│  Display Name*: [Kancelaria Sejmu____]                   │
│                                                           │
│  Primary Language*:  ○ Polish  ○ English                 │
│                                                           │
│  Channel Type:  ⚫ Political  ○ Gaming  ○ IRL  ○ Other   │
│                                                           │
│  ┌─ Platform Information ──────────────────────────────┐ │
│  │ Platform: [YouTube ▼]                               │ │
│  │ Channel ID: [UCWd8gHV5Qt-bBa4dI98cS0Q____________] │ │
│  │ (auto-filled from current channel)                  │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                           │
│  [Cancel]                              [Create Profile]   │
└───────────────────────────────────────────────────────────┘
```

**Generated YAML:**
```yaml
streamer_id: sejm
name: "Kancelaria Sejmu"
aliases: []

content:
  primary_language: pl
  channel_type: political
  primary_platform: youtube

platforms:
  youtube:
    channel_id: "UCWd8gHV5Qt-bBa4dI98cS0Q"

generation:
  context_model: "gpt-4o-mini"
  title_model: "gpt-4o"
  description_model: "gpt-4o"
  temperature: 0.8

seed_examples: []
```

**Kod:**
```python
class CreateProfileDialog(QDialog):
    """Dialog for creating new streamer profile"""

    def __init__(self, parent, channel_id: str = None):
        super().__init__(parent)
        self.channel_id = channel_id
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Create New Streamer Profile")
        layout = QVBoxLayout()

        # Streamer ID
        layout.addWidget(QLabel("Streamer ID* (lowercase, no spaces):"))
        self.id_input = QLineEdit()
        self.id_input.setPlaceholderText("e.g., sejm, asmongold, pokimane")
        layout.addWidget(self.id_input)

        # Display Name
        layout.addWidget(QLabel("Display Name*:"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g., Kancelaria Sejmu")
        layout.addWidget(self.name_input)

        # Language
        lang_layout = QHBoxLayout()
        lang_layout.addWidget(QLabel("Primary Language*:"))
        self.lang_group = QButtonGroup()

        pl_radio = QRadioButton("Polish")
        en_radio = QRadioButton("English")
        self.lang_group.addButton(pl_radio, 0)
        self.lang_group.addButton(en_radio, 1)
        pl_radio.setChecked(True)

        lang_layout.addWidget(pl_radio)
        lang_layout.addWidget(en_radio)
        layout.addLayout(lang_layout)

        # Channel Type
        layout.addWidget(QLabel("Channel Type:"))
        self.type_combo = QComboBox()
        self.type_combo.addItems(["Political", "Gaming", "IRL", "Educational", "Other"])
        layout.addWidget(self.type_combo)

        # Platform Info
        platform_group = QGroupBox("Platform Information")
        platform_layout = QVBoxLayout()

        platform_layout.addWidget(QLabel("Platform:"))
        self.platform_combo = QComboBox()
        self.platform_combo.addItems(["YouTube", "Twitch", "Kick"])
        platform_layout.addWidget(self.platform_combo)

        platform_layout.addWidget(QLabel("Channel ID:"))
        self.channel_id_input = QLineEdit()
        if self.channel_id:
            self.channel_id_input.setText(self.channel_id)
        platform_layout.addWidget(self.channel_id_input)

        platform_group.setLayout(platform_layout)
        layout.addWidget(platform_group)

        # Buttons
        button_layout = QHBoxLayout()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        create_btn = QPushButton("Create Profile")
        create_btn.clicked.connect(self.create_profile)
        create_btn.setDefault(True)
        button_layout.addWidget(create_btn)

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def create_profile(self):
        """Validate and create profile"""
        streamer_id = self.id_input.text().strip().lower()
        name = self.name_input.text().strip()

        # Validation
        if not streamer_id:
            QMessageBox.warning(self, "Validation Error", "Streamer ID is required")
            return

        if ' ' in streamer_id:
            QMessageBox.warning(self, "Validation Error", "Streamer ID cannot contain spaces")
            return

        if not name:
            QMessageBox.warning(self, "Validation Error", "Display Name is required")
            return

        # Get selections
        lang = "pl" if self.lang_group.checkedId() == 0 else "en"
        channel_type = self.type_combo.currentText().lower()
        platform = self.platform_combo.currentText().lower()
        platform_id = self.channel_id_input.text().strip()

        # Build profile data
        profile_data = {
            "streamer_id": streamer_id,
            "name": name,
            "aliases": [],
            "content": {
                "primary_language": lang,
                "channel_type": channel_type,
                "primary_platform": platform
            },
            "platforms": {
                platform: {
                    "channel_id" if platform == "youtube" else "username": platform_id
                }
            },
            "generation": {
                "context_model": "gpt-4o-mini",
                "title_model": "gpt-4o",
                "description_model": "gpt-4o",
                "temperature": 0.8
            },
            "seed_examples": []
        }

        # Create via StreamerManager
        try:
            from pipeline.streamers import get_manager
            manager = get_manager()
            manager.create(profile_data)

            QMessageBox.information(
                self,
                "Success",
                f"Profile '{name}' created successfully!\n\n"
                f"Saved to: pipeline/streamers/profiles/{streamer_id}.yaml"
            )

            self.accept()

        except ValueError as e:
            QMessageBox.warning(self, "Error", str(e))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create profile: {e}")
```

---

## Implementation Priority

### Phase 1: Basic Detection Info (1-2h)
- ✅ Add profile info bar to YouTube Upload tab
- ✅ Auto-detect and display current profile
- ✅ Show warning if no profile found
- ✅ Add "Change Profile..." button

### Phase 2: Profile Selection Dialog (2-3h)
- ✅ ProfileSelectionDialog with list of all profiles
- ✅ "Remember for this channel" checkbox
- ✅ Save channel_id → streamer_id mapping
- ✅ "Skip (Legacy)" option for backwards compatibility

### Phase 3: Create Profile Dialog (2-3h)
- ✅ CreateProfileDialog with form
- ✅ Validation
- ✅ YAML generation via StreamerManager.create()
- ✅ Auto-reload after creation

### Phase 4: Polish & Testing (1h)
- ✅ Error handling
- ✅ User feedback messages
- ✅ Integration testing with Stage 09

**Total Estimated Time: 6-9 hours**

---

## Key Design Decisions

### Decision 1: Where to store channel_id mappings?

**Option A:** Add to existing profile YAML
```yaml
# pipeline/streamers/profiles/sejm.yaml
platforms:
  youtube:
    channel_id: "UCWd8gHV5Qt-bBa4dI98cS0Q"  # Already exists
```
**Pros:** ✅ No extra file
**Cons:** ❌ Limited to 1 channel per platform per profile

**Option B:** Separate mapping file
```yaml
# config/channel_mappings.yaml
"UCWd8gHV5Qt-bBa4dI98cS0Q": "sejm"
"UC47Ulzsc_c5YRhoZVNW65Xg": "asmongold"
```
**Pros:** ✅ Multiple channels → same profile
**Cons:** ⚠️ Extra file to manage

**Recommendation:** Option B (more flexible)

---

### Decision 2: When to show dialog?

**Option A:** Always auto-show if no profile
**Option B:** Show warning, require manual click

**Recommendation:** Option A (better UX, prevents silent failure)

---

### Decision 3: Content type detection in GUI?

**Future enhancement:** Add content type selector to upload dialog
```
Content Type: [Sejm Meeting PL ▼]
              [Sejm Press Conference PL]
              [Sejm Briefing PL]
              [Auto-detect]
```

**For now:** Auto-detection only (via ContentTypeClassifier)

---

## Testing Scenarios

### Scenario 1: Existing profile found ✅
1. User opens YouTube Upload tab
2. System detects profile = sejm
3. Info bar shows: "🤖 Auto-detected: Sejm"
4. Upload proceeds normally

### Scenario 2: No profile found ⚠️
1. User opens YouTube Upload tab
2. System detects profile = None
3. Dialog auto-shows: "No profile found"
4. User selects from list OR creates new
5. Upload proceeds with selected profile

### Scenario 3: Create new profile ➕
1. User clicks "Create New Profile"
2. Fills form: ID, name, language, channel
3. Clicks "Create Profile"
4. YAML saved to profiles/
5. Profile available immediately

### Scenario 4: Change profile manually 🔄
1. User clicks "Change Profile..."
2. Dialog shows with current selection highlighted
3. User picks different profile
4. ✅ Checkbox "Remember" saves mapping
5. Future uploads use new profile

---

## Backwards Compatibility

**Without StreamerManager installed:**
- Info bar shows: "ℹ️ Legacy mode (no streamer profiles)"
- Upload uses legacy title/description generation
- No errors thrown

**With StreamerManager but no profiles:**
- Shows: "⚠️ No profiles found. Create one to use AI metadata."
- "Create New Profile" button available

---

## Summary

**Recommended Approach: Option 3 (Hybrid)**

✅ Auto-detect gdy możliwe
✅ Dialog gdy potrzebne
✅ Manual override dostępny
✅ Create new profile in GUI
✅ Remember wybór per channel
✅ Backwards compatible

**Implementation: ~6-9 godzin**

Czy to podejście ma sens? Coś do zmiany?
