package launcher

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
)

type RunOptions struct {
	DryRun bool
	Stdout io.Writer
	Stderr io.Writer
}

func Run(ctx context.Context, cfg Config, opts RunOptions) error {
	plan, err := cfg.BuildPlan()
	if err != nil {
		return err
	}
	if opts.Stdout == nil {
		opts.Stdout = os.Stdout
	}
	if opts.Stderr == nil {
		opts.Stderr = os.Stderr
	}
	if opts.DryRun {
		enc := json.NewEncoder(opts.Stdout)
		enc.SetIndent("", "  ")
		return enc.Encode(plan)
	}
	if err := cfg.Validate(true); err != nil {
		return err
	}
	if err := ensureExecutable(cfg.BrowserBinary); err != nil {
		return err
	}
	if err := os.MkdirAll(plan.UserDataDir, 0755); err != nil {
		return fmt.Errorf("create user_data_dir: %w", err)
	}
	lock, err := AcquireProfileLock(plan.UserDataDir)
	if err != nil {
		return err
	}
	defer lock.Release()
	cmd := exec.CommandContext(ctx, cfg.BrowserBinary, plan.Args...)
	cmd.Stdout = opts.Stdout
	cmd.Stderr = opts.Stderr
	cmd.Env = os.Environ()
	for k, v := range cfg.Env {
		cmd.Env = append(cmd.Env, k+"="+v)
	}
	return cmd.Run()
}

func ensureExecutable(path string) error {
	info, err := os.Stat(path)
	if err != nil {
		return fmt.Errorf("browser binary not accessible: %w", err)
	}
	if info.IsDir() {
		return errors.New("browser binary path is a directory")
	}
	if info.Mode()&0111 == 0 {
		return errors.New("browser binary is not executable")
	}
	return nil
}

type ProfileLock struct {
	path string
	file *os.File
}

func AcquireProfileLock(userDataDir string) (*ProfileLock, error) {
	if err := os.MkdirAll(userDataDir, 0755); err != nil {
		return nil, fmt.Errorf("create user_data_dir before lock: %w", err)
	}
	path := filepath.Join(userDataDir, ".browseforge-runtime.lock")
	file, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if err != nil {
		if errors.Is(err, os.ErrExist) {
			return nil, fmt.Errorf("profile is already locked: %s", path)
		}
		return nil, fmt.Errorf("create profile lock: %w", err)
	}
	_, _ = fmt.Fprintf(file, "pid=%d\n", os.Getpid())
	return &ProfileLock{path: path, file: file}, nil
}

func (l *ProfileLock) Release() error {
	if l == nil {
		return nil
	}
	var err error
	if l.file != nil {
		err = l.file.Close()
	}
	if rmErr := os.Remove(l.path); rmErr != nil && !errors.Is(rmErr, os.ErrNotExist) && err == nil {
		err = rmErr
	}
	return err
}
