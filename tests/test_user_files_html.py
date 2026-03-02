from __future__ import annotations

import json
from unittest.mock import patch

from osx_system_agent.reports.user_files_html import (
    _build_clusters,
    _build_cross_location,
    _build_recommendations,
    _classify_cluster,
    _location_key,
    _location_label,
    _shorten_path,
    generate_user_files_report,
)


class TestShortenPath:
    def test_short_path_unchanged(self) -> None:
        assert _shorten_path("/Users/foo/bar.txt") == "/Users/foo/bar.txt"

    def test_onedrive_prefix_stripped(self) -> None:
        p = (
            "/Users/douglas_brush/Library/CloudStorage/OneDrive-BrushCyber"
            "/Some/Deep/Nested/Directory/Structure/With/Lots/Of/Segments/file.csv"
        )
        result = _shorten_path(p)
        assert result.startswith("~/")
        assert "file.csv" in result

    def test_long_path_truncated(self) -> None:
        p = "/Users/douglas_brush/" + "a" * 200 + "/file.txt"
        result = _shorten_path(p, max_len=80)
        assert len(result) <= 80
        assert result.startswith("...")


class TestLocationLabel:
    def test_cloud_storage(self) -> None:
        assert _location_label(
            "/Users/douglas_brush/Library/CloudStorage"
        ) == "Cloud Storage"

    def test_documents(self) -> None:
        assert _location_label("/Users/douglas_brush/Documents") == "Documents"

    def test_unknown(self) -> None:
        assert _location_label("/tmp/foo") == "/tmp/foo"


class TestBuildRecommendations:
    def test_returns_list(self) -> None:
        data = {
            "total_size": 1000,
            "categories": {},
            "duplicates": {
                "total_groups": 5,
                "total_duplicate_files": 10,
                "total_wasted": 500,
                "total_wasted_human": "500B",
                "by_category": {},
                "groups": [],
            },
            "locations": {},
        }
        recs = _build_recommendations(data)
        assert isinstance(recs, list)
        assert len(recs) >= 1  # At least the summary rec

    def test_enagic_recommendation(self) -> None:
        data = {
            "total_size": 1_000_000_000,
            "categories": {},
            "duplicates": {
                "total_groups": 10,
                "total_duplicate_files": 20,
                "total_wasted": 800_000_000,
                "total_wasted_human": "800MB",
                "by_category": {},
                "groups": [
                    {
                        "wasted": 700_000_000,
                        "files": [
                            {"name": "ENANAS_inventory.csv", "dir": "/foo/Enagic"},
                        ],
                    },
                ],
            },
            "locations": {},
        }
        recs = _build_recommendations(data)
        enagic_recs = [r for r in recs if "Enagic" in r]
        assert len(enagic_recs) >= 1


class TestClassifyCluster:
    def test_enagic(self) -> None:
        g = {"files": [{"path": "/foo/Enagic/bar.csv", "dir": "/foo/Enagic"}], "wasted": 100}
        assert _classify_cluster(g) == "Enagic / Project Fuji"

    def test_denali(self) -> None:
        g = {"files": [{"path": "/foo/Denali/doc.pdf", "dir": "/foo/Denali"}], "wasted": 100}
        assert _classify_cluster(g) == "Denali (Google Litigation)"

    def test_mkr(self) -> None:
        g = {"files": [{"path": "/foo/MKR/file.png", "dir": "/foo/MKR"}], "wasted": 100}
        assert _classify_cluster(g) == "MKR / Miers DFIR"

    def test_local_documents(self) -> None:
        doc_path = "/Users/douglas_brush/Documents/a.pdf"
        g = {
            "files": [{"path": doc_path, "dir": "/Users/douglas_brush/Documents"}],
            "wasted": 100,
        }
        assert _classify_cluster(g) == "Local Documents"

    def test_photos(self) -> None:
        pic_path = "/Users/douglas_brush/Pictures/img.jpg"
        g = {
            "files": [{"path": pic_path, "dir": "/Users/douglas_brush/Pictures"}],
            "wasted": 50,
        }
        assert _classify_cluster(g) == "Photos / Pictures"


class TestLocationKey:
    def test_sharepoint(self) -> None:
        assert _location_key("/foo/OneDrive-SharedLibraries-BrushCyber/bar") == "SharePoint"

    def test_onedrive(self) -> None:
        assert _location_key("/foo/OneDrive-BrushCyber/bar") == "OneDrive"

    def test_documents(self) -> None:
        assert _location_key("/Users/x/Documents/file.pdf") == "Documents"


class TestBuildClusters:
    def test_groups_by_cluster(self) -> None:
        groups = [
            {"files": [{"path": "/x/Enagic/a.csv", "dir": "/x/Enagic"}], "wasted": 100},
            {"files": [{"path": "/x/Enagic/b.csv", "dir": "/x/Enagic"}], "wasted": 200},
            {"files": [{"path": "/x/Denali/c.pdf", "dir": "/x/Denali"}], "wasted": 50},
        ]
        clusters = _build_clusters(groups)
        assert "Enagic / Project Fuji" in clusters
        assert len(clusters["Enagic / Project Fuji"]) == 2
        assert "Denali (Google Litigation)" in clusters


class TestBuildCrossLocation:
    def test_detects_cross_location(self) -> None:
        groups = [
            {
                "files": [
                    {"path": "/x/OneDrive-BrushCyber/a.pdf"},
                    {"path": "/x/OneDrive-SharedLibraries-BrushCyber/a.pdf"},
                ],
                "wasted": 1000,
            },
        ]
        result = _build_cross_location(groups)
        assert len(result) == 1
        assert "OneDrive" in result[0][0]
        assert "SharePoint" in result[0][0]

    def test_same_location_excluded(self) -> None:
        groups = [
            {
                "files": [
                    {"path": "/x/OneDrive-BrushCyber/a.pdf"},
                    {"path": "/x/OneDrive-BrushCyber/b.pdf"},
                ],
                "wasted": 500,
            },
        ]
        result = _build_cross_location(groups)
        assert len(result) == 0


class TestGenerateReport:
    @patch("osx_system_agent.reports.user_files_html._logo_data_uri", return_value="")
    def test_generates_html(self, mock_logo, tmp_path) -> None:
        scan_data = {
            "generated_at": "2026-03-01T00:00:00+00:00",
            "total_files": 100,
            "total_size": 1_000_000,
            "total_size_human": "976.6KB",
            "categories": {
                "Documents": {"count": 50, "size": 500_000, "size_human": "488.3KB"},
                "Images": {"count": 50, "size": 500_000, "size_human": "488.3KB"},
            },
            "extensions": {
                "pdf": {"count": 30, "size": 300_000, "size_human": "292.9KB"},
                "png": {"count": 20, "size": 200_000, "size_human": "195.3KB"},
            },
            "locations": {
                "/Users/douglas_brush/Documents": {
                    "count": 100, "size": 1_000_000, "size_human": "976.6KB",
                },
            },
            "duplicates": {
                "total_groups": 5,
                "total_duplicate_files": 8,
                "total_wasted": 50_000,
                "total_wasted_human": "48.8KB",
                "by_category": {
                    "Documents": {
                        "groups": 3, "files": 5,
                        "wasted": 30_000, "wasted_human": "29.3KB",
                    },
                },
                "groups": [
                    {
                        "match_type": "sha256",
                        "count": 2,
                        "size": 10_000,
                        "wasted": 10_000,
                        "wasted_human": "9.8KB",
                        "category": "Documents",
                        "files": [
                            {"path": "/Users/a/b.pdf", "name": "b.pdf", "dir": "/Users/a"},
                            {"path": "/Users/c/b.pdf", "name": "b.pdf", "dir": "/Users/c"},
                        ],
                    },
                ],
            },
            "largest_files": [
                {
                    "path": "/Users/douglas_brush/Documents/big.pdf",
                    "size": 500_000,
                    "size_human": "488.3KB",
                    "category": "Documents",
                    "ext": "pdf",
                },
            ],
            "top_directories": [
                {
                    "path": "/Users/douglas_brush/Documents",
                    "count": 100,
                    "size": 1_000_000,
                    "size_human": "976.6KB",
                },
            ],
        }

        scan_json = tmp_path / "scan.json"
        scan_json.write_text(json.dumps(scan_data))

        report_path = generate_user_files_report(scan_json, tmp_path)
        assert report_path.exists()
        assert report_path.suffix == ".html"

        content = report_path.read_text()
        assert "<!DOCTYPE html>" in content
        assert "User File Inventory" in content
        assert "Executive Summary" in content
        assert "Remediation Plan" in content
        assert "100" in content  # total files
        assert "Documents" in content
        assert "SHA-256" in content
