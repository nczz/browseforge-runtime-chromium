package stealth

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"net/netip"
	"os"
	"strings"
)

const SchemaVersion = "1.0"

type PersonaConfig struct {
	SchemaVersion string           `json:"schema_version"`
	RuntimeID     string           `json:"runtime_id"`
	Seed          uint64           `json:"seed"`
	Browser       BrowserIdentity  `json:"browser"`
	Platform      PlatformIdentity `json:"platform"`
	Locale        LocaleIdentity   `json:"locale"`
	Hardware      HardwareIdentity `json:"hardware"`
	Screen        ScreenIdentity   `json:"screen"`
	GPU           GPUIdentity      `json:"gpu"`
	WebRTC        WebRTCPolicy     `json:"webrtc"`
	Storage       StoragePolicy    `json:"storage"`
}

type BrowserIdentity struct {
	Family      string   `json:"family"`
	Major       int      `json:"major"`
	FullVersion string   `json:"full_version"`
	Brands      []string `json:"brands"`
	UserAgent   string   `json:"user_agent"`
}

type PlatformIdentity struct {
	OS         string `json:"os"`
	Arch       string `json:"arch"`
	Platform   string `json:"platform"`
	PlatformCH string `json:"platform_ch"`
	Mobile     bool   `json:"mobile"`
	Bitness    string `json:"bitness"`
	Model      string `json:"model"`
}

type LocaleIdentity struct {
	Timezone       string `json:"timezone"`
	Locale         string `json:"locale"`
	AcceptLanguage string `json:"accept_language"`
}

type HardwareIdentity struct {
	HardwareConcurrency int `json:"hardware_concurrency"`
	DeviceMemoryGB      int `json:"device_memory_gb"`
}

type ScreenIdentity struct {
	Width       int     `json:"width"`
	Height      int     `json:"height"`
	AvailWidth  int     `json:"avail_width"`
	AvailHeight int     `json:"avail_height"`
	DPR         float64 `json:"dpr"`
	ColorDepth  int     `json:"color_depth"`
}

type GPUIdentity struct {
	Vendor       string            `json:"vendor"`
	Renderer     string            `json:"renderer"`
	ANGLEBackend string            `json:"angle_backend"`
	WebGLParams  map[string]string `json:"webgl_params,omitempty"`
}

type WebRTCPolicy struct {
	Mode              string `json:"mode"`
	ProxyRegion       string `json:"proxy_region"`
	DirectIPRedaction bool   `json:"direct_ip_redaction"`
}

type StoragePolicy struct {
	QuotaMB    int  `json:"quota_mb"`
	Persistent bool `json:"persistent"`
}

type PersonaSnapshot struct {
	PersonaConfig
	PersonaIDHash string `json:"persona_id_hash"`
	OriginSaltKey string `json:"origin_salt_key"`
}

func LoadConfig(path string) (PersonaConfig, error) {
	var cfg PersonaConfig
	data, err := os.ReadFile(path)
	if err != nil {
		return cfg, err
	}
	if err := json.Unmarshal(data, &cfg); err != nil {
		return cfg, err
	}
	return cfg, nil
}

func Resolve(cfg PersonaConfig) (PersonaSnapshot, error) {
	if err := Validate(cfg); err != nil {
		return PersonaSnapshot{}, err
	}
	canonical, err := json.Marshal(cfg)
	if err != nil {
		return PersonaSnapshot{}, err
	}
	personaHash := sha256.Sum256(canonical)
	originKey := hmac.New(sha256.New, []byte(fmt.Sprintf("browseforge-origin-salt:%d", cfg.Seed)))
	originKey.Write(canonical)
	return PersonaSnapshot{
		PersonaConfig: cfg,
		PersonaIDHash: hex.EncodeToString(personaHash[:16]),
		OriginSaltKey: hex.EncodeToString(originKey.Sum(nil)[:16]),
	}, nil
}

func Validate(cfg PersonaConfig) error {
	var missing []string
	require := func(ok bool, field string) {
		if !ok {
			missing = append(missing, field)
		}
	}
	require(cfg.SchemaVersion == SchemaVersion, "schema_version")
	require(cfg.RuntimeID == "browseforge-chromium", "runtime_id")
	require(cfg.Seed != 0, "seed")
	require(cfg.Browser.Family == "chromium", "browser.family")
	require(cfg.Browser.Major > 0, "browser.major")
	require(cfg.Browser.FullVersion != "", "browser.full_version")
	require(cfg.Browser.UserAgent != "", "browser.user_agent")
	require(cfg.Platform.OS != "", "platform.os")
	require(cfg.Platform.Arch != "", "platform.arch")
	require(cfg.Platform.Platform != "", "platform.platform")
	require(cfg.Platform.PlatformCH != "", "platform.platform_ch")
	require(cfg.Locale.Timezone != "", "locale.timezone")
	require(cfg.Locale.Locale != "", "locale.locale")
	require(cfg.Locale.AcceptLanguage != "", "locale.accept_language")
	require(cfg.Hardware.HardwareConcurrency > 0, "hardware.hardware_concurrency")
	require(cfg.Hardware.DeviceMemoryGB > 0, "hardware.device_memory_gb")
	require(cfg.Screen.Width > 0, "screen.width")
	require(cfg.Screen.Height > 0, "screen.height")
	require(cfg.Screen.AvailWidth > 0, "screen.avail_width")
	require(cfg.Screen.AvailHeight > 0, "screen.avail_height")
	require(cfg.Screen.DPR > 0, "screen.dpr")
	require(cfg.Screen.ColorDepth > 0, "screen.color_depth")
	require(cfg.GPU.Vendor != "", "gpu.vendor")
	require(cfg.GPU.Renderer != "", "gpu.renderer")
	require(cfg.WebRTC.Mode != "", "webrtc.mode")
	require(cfg.Storage.QuotaMB > 0, "storage.quota_mb")
	if len(missing) > 0 {
		return fmt.Errorf("persona config incomplete; fail closed: %s", strings.Join(missing, ", "))
	}
	if cfg.Screen.AvailWidth > cfg.Screen.Width || cfg.Screen.AvailHeight > cfg.Screen.Height {
		return errors.New("persona config incoherent; screen available size exceeds screen size")
	}
	if cfg.WebRTC.ProxyRegion != "" && !validProxyRegion(cfg.WebRTC.ProxyRegion) {
		return fmt.Errorf("persona config incoherent; invalid WebRTC proxy region %q", cfg.WebRTC.ProxyRegion)
	}
	return nil
}

func validProxyRegion(region string) bool {
	if region == "" || strings.TrimSpace(region) != region || len(region) > 64 {
		return false
	}
	if _, err := netip.ParseAddr(region); err == nil {
		return false
	}
	for i := range len(region) {
		c := region[i]
		switch {
		case c >= 'a' && c <= 'z':
		case c >= 'A' && c <= 'Z':
		case c >= '0' && c <= '9':
		case c == '-' || c == '_' || c == '.':
		default:
			return false
		}
	}
	return true
}
