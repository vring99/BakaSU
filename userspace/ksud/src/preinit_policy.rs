//! Platform-independent decisions shared by preinit staging and status reporting.

use std::{
    collections::{BTreeMap, HashMap},
    fs,
    path::{Path, PathBuf},
};

pub const BOOTCOUNT_LIMIT: u64 = 3;

#[derive(Debug, PartialEq, Eq)]
pub enum Storage {
    Vold,
    Watchdog,
    Default,
}

pub const fn storage(uapi_version: u32, vold: bool, watchdog: bool) -> Storage {
    if uapi_version >= 6 && vold {
        Storage::Vold
    } else if watchdog {
        Storage::Watchdog
    } else {
        Storage::Default
    }
}

pub fn next_boot_modules(dirs: &[&Path]) -> BTreeMap<String, PathBuf> {
    let mut modules: BTreeMap<String, Option<PathBuf>> = BTreeMap::new();
    for dir in dirs {
        let Ok(entries) = fs::read_dir(dir) else {
            continue;
        };
        for entry in entries.flatten() {
            let path = entry.path();
            if !path.is_dir() {
                continue;
            }
            let Some(id) = path.file_name().and_then(|s| s.to_str()) else {
                continue;
            };
            let id = id.to_owned();
            if path.join("disable").exists() || path.join("remove").exists() {
                modules.insert(id, None);
            } else {
                modules.entry(id).or_insert(Some(path));
            }
        }
    }
    modules
        .into_iter()
        .filter_map(|(id, path)| path.map(|path| (id, path)))
        .collect()
}

pub const fn disabled_by_bootloop(count: u64) -> bool {
    count > BOOTCOUNT_LIMIT
}

pub const fn reset_after_success(count: u64) -> bool {
    count > 0 && !disabled_by_bootloop(count)
}

pub fn module_states(content: &str, bootcount: u64) -> HashMap<String, String> {
    content
        .lines()
        .filter_map(|line| {
            let mut parts = line.splitn(3, ' ');
            let id = parts.next()?;
            let state = parts.next()?;
            let state = if disabled_by_bootloop(bootcount) && state == "ok" {
                "bootloop"
            } else {
                state
            };
            Some((id.to_owned(), state.to_owned()))
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};

    static SEQUENCE: AtomicUsize = AtomicUsize::new(0);

    struct Tree(PathBuf);

    impl Tree {
        fn new() -> Self {
            let root = std::env::current_exe()
                .unwrap()
                .parent()
                .unwrap()
                .join(format!(
                    "preinit-policy-{}-{}",
                    std::process::id(),
                    SEQUENCE.fetch_add(1, Ordering::Relaxed)
                ));
            fs::create_dir(&root).unwrap();
            Self(root)
        }

        fn module(&self, tree: &str, id: &str, marker: Option<&str>) -> PathBuf {
            let dir = self.0.join(tree).join(id);
            fs::create_dir_all(&dir).unwrap();
            if let Some(marker) = marker {
                fs::write(dir.join(marker), "").unwrap();
            }
            dir
        }

        fn collect(&self) -> BTreeMap<String, PathBuf> {
            next_boot_modules(&[&self.0.join("updates"), &self.0.join("live")])
        }
    }

    impl Drop for Tree {
        fn drop(&mut self) {
            fs::remove_dir_all(&self.0).unwrap();
        }
    }

    #[test]
    fn vold_requires_kernel_support_and_retains_legacy_fallbacks() {
        assert_eq!(storage(6, true, true), Storage::Vold);
        assert_eq!(storage(7, true, false), Storage::Vold);
        assert_eq!(storage(5, true, true), Storage::Watchdog);
        assert_eq!(storage(5, true, false), Storage::Default);
        assert_eq!(storage(6, false, true), Storage::Watchdog);
        assert_eq!(storage(6, false, false), Storage::Default);
    }

    #[test]
    fn pending_update_wins_over_live_content() {
        let tree = Tree::new();
        tree.module("live", "module", None);
        let updated = tree.module("updates", "module", None);
        fs::write(updated.join("payload"), "new preinit content").unwrap();
        assert_eq!(tree.collect().get("module"), Some(&updated));
    }

    #[test]
    fn disable_or_remove_in_either_tree_vetoes_next_boot() {
        for marker in ["disable", "remove"] {
            for marked in ["live", "updates"] {
                let tree = Tree::new();
                tree.module("live", "module", None);
                tree.module("updates", "module", None);
                tree.module(marked, "module", Some(marker));
                assert!(tree.collect().is_empty(), "{marker} in {marked}");
            }
        }
    }

    #[test]
    fn missing_trees_and_non_directories_are_ignored_and_modules_are_sorted() {
        let tree = Tree::new();
        assert!(tree.collect().is_empty());
        tree.module("live", "z-last", None);
        tree.module("live", "a-first", None);
        fs::write(tree.0.join("live/not-a-module"), "").unwrap();
        assert_eq!(
            tree.collect().keys().cloned().collect::<Vec<_>>(),
            ["a-first", "z-last"]
        );
    }

    #[test]
    fn successful_boot_resets_attempts_but_keeps_parked_bootloops() {
        assert!(!reset_after_success(0));
        for count in 1..=BOOTCOUNT_LIMIT {
            assert!(reset_after_success(count));
            assert!(!disabled_by_bootloop(count));
        }
        assert!(disabled_by_bootloop(BOOTCOUNT_LIMIT + 1));
        assert!(!reset_after_success(BOOTCOUNT_LIMIT + 1));
    }

    #[test]
    fn bootloop_overrides_only_successfully_staged_modules() {
        let content = "good ok \nlarge no_space need 999\nbad error missing conf\nold unsupported old kernel\nmalformed\n";
        let normal = module_states(content, BOOTCOUNT_LIMIT);
        assert_eq!(normal["good"], "ok");
        let parked = module_states(content, BOOTCOUNT_LIMIT + 1);
        assert_eq!(parked["good"], "bootloop");
        assert_eq!(parked["large"], "no_space");
        assert_eq!(parked["bad"], "error");
        assert_eq!(parked["old"], "unsupported");
        assert!(!parked.contains_key("malformed"));
    }
}
