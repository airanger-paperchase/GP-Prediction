import React, { useState, useMemo, useRef, useEffect } from "react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Pagination, PaginationContent, PaginationItem, PaginationLink, PaginationNext, PaginationPrevious } from "@/components/ui/pagination";
import { BarChart3, Database, Download, Loader2, Sparkles, TrendingUp, Users, FileText } from "lucide-react";
import { resolveCompanyCode, resolveUsername } from "@/lib/config";

import { useToast } from "@/hooks/use-toast";
import axios from "axios";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

const API_BASE = "http://localhost:8007";

const SqlPlMasterMapping: React.FC = () => {
  const [saving, setSaving] = useState(false);
  
  const { toast } = useToast();
  const [sqlCompanyCode, setSqlCompanyCode] = useState("");
  const [sqlUsername, setSqlUsername] = useState("");
  const [sqlLoading, setSqlLoading] = useState(false);
  const [langextractResult, setLangextractResult] = useState<any>(null);
  const [finalCsv, setFinalCsv] = useState<string>("");
  const [editableRows, setEditableRows] = useState<any[]>([]);
  const [currentPage, setCurrentPage] = useState(1);
  const summaryRef = useRef<HTMLDivElement>(null);
  const topRef = useRef<HTMLDivElement>(null);
  const [showDownArrow, setShowDownArrow] = useState(false);
  const [isSummaryInView, setIsSummaryInView] = useState(false);
  // Observe summary box visibility
  useEffect(() => {
    const summaryEl = summaryRef.current;
    if (!summaryEl) return;
    const observer = new window.IntersectionObserver(
      ([entry]) => {
        setIsSummaryInView(entry.isIntersecting);
      },
      { root: null, threshold: 0.5 }
    );
    observer.observe(summaryEl);
    return () => observer.disconnect();
  }, [finalCsv]);
  const [showUpArrow, setShowUpArrow] = useState(false);
  const ITEMS_PER_PAGE = 20;

  // Listen for messages from iframe
  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      // Always verify the origin for security
      if (event.origin !== window.location.origin) return;

      if (event.data.type === "SET_CREDENTIALS") {
        const { companyCode, username } = event.data;
        setSqlCompanyCode(companyCode);
        setSqlUsername(username);
      }
    };

    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, []);

  useEffect(() => {
    const companyCode = resolveCompanyCode();
    const username = resolveUsername();
    
    if (companyCode) setSqlCompanyCode(companyCode);
    if (username) setSqlUsername(username);

    // Auto-trigger data loading if both parameters are present
    if (companyCode && username) {
      const timer = setTimeout(() => {
        handleSqlMapping();
      }, 500);
      return () => clearTimeout(timer);
    }
  }, []);

  const totalPages = Math.ceil(editableRows.length / ITEMS_PER_PAGE);
  const paginatedRows = useMemo(() => {
    const startIndex = (currentPage - 1) * ITEMS_PER_PAGE;
    return editableRows.slice(startIndex, startIndex + ITEMS_PER_PAGE);
  }, [editableRows, currentPage]);

// Calculate summary counts for editableRows
  const summaryCounts = React.useMemo(() => {
    if (!editableRows || editableRows.length === 0) return null;
    let mapped_existing = 0;
    let predicted = 0;
    editableRows.forEach(row => {
      if (row.source === "existing") mapped_existing++;
      else predicted++;
    });
    const total = editableRows.length;
    const mapped_percent = total > 0 ? mapped_existing / total : 0;
    return { total, mapped_existing, predicted, mapped_percent };
  }, [editableRows]);

  // Use finalCsv to display the table and auto-scroll to summary
  useEffect(() => {
    if (finalCsv) {
      const rows: any[] = [];
      const csvLines = finalCsv.split(/\r?\n/);
      const headers = csvLines[0]?.split(",");
      for (let i = 1; i < csvLines.length; i++) {
        const line = csvLines[i];
        if (!line.trim()) continue;
        const values = line.split(",");
        const rowObj: any = {};
        headers.forEach((h, idx) => {
          rowObj[h] = values[idx] ?? "";
        });
        rowObj.line_item = rowObj.LineItem ?? rowObj.line_item ?? "";
        rowObj.parent = rowObj.Parent ?? rowObj.parent ?? "";
        rowObj.grandparent = rowObj.GrandParent ?? rowObj.grandparent ?? "";
        rowObj.source = "finalCsv";
        rows.push(rowObj);
      }
      setEditableRows(rows);
    //   setShowDownArrow(true);
      // Auto-scroll to summary
      setTimeout(() => {
        if (summaryRef.current) {
          summaryRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      }, 300);
    } else {
      setEditableRows([]);
      setShowDownArrow(false);
    }
  }, [finalCsv]);

  // Show up arrow when scrolled down
  useEffect(() => {
    const handleScroll = () => {
      setShowUpArrow(window.scrollY > 200);
    };
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const handleEditCell = (rowIdx: number, field: string, value: string) => {
    setEditableRows(prev => prev.map((row, idx) => idx === rowIdx ? { ...row, [field]: value } : row));
  };

  const handleSqlMapping = async () => {
    if (!sqlCompanyCode || !sqlUsername) {
      toast({
        title: "Missing Information",
        description: "Please enter both company code and username.",
        variant: "destructive",
      });
      return;
    }
    setSqlLoading(true);
    try {
      const resp = await axios.post(`${API_BASE}/glmapapi/get_plmaster_mapping`, {
        company_code: sqlCompanyCode,
        username: sqlUsername,
      });
      const result = resp.data;
      setFinalCsv(result.final_csv || "");
      if (result && Array.isArray(result.only_lineitems) && result.only_lineitems.length > 0) {
        // If you want to show predictions separately, you can use result.predictions
        setLangextractResult({ results: result.predictions });
      } else {
        setLangextractResult(null);
      }
      toast({
        title: "Success",
        description: "PLMaster mapping and missing lineitems processed.",
        variant: "default",
      });
    } catch (e: any) {
      toast({
        title: "Error",
        description: `SQL mapping failed: ${e?.response?.data?.detail || e?.message || e}`,
        variant: "destructive",
      });
    } finally {
      setSqlLoading(false);
    }
  };

  return (
<div
    ref={topRef}
    className="min-h-screen p-6 relative "
    style={{
        background: "linear-gradient(90deg, #E4E1F0 0%, #E7EAFA 50%, #E8EEFE 100%)",
    }}
>

        {/* Left side images - always show first, second only if data is present, adjust position if no data */}
        {/* <div
            key="left-img-0"
            className="absolute left-0 z-0 opacity-70 pointer-events-none"
            style={{
                top: editableRows.length > 0 ? `4%` : `16%`,
                transform: "translateY(-20%)",
            }}
        >
            <img
                src="/abstract1.webp"
                alt="abstract left 0"
                className="w-[500px] h-[500px] object-contain"
                style={{ filter: "blur(0.5px)" }}
            />
        </div>
        {editableRows.length > 0 && (
            <div
                key="left-img-1"
                className="absolute left-0 z-0 opacity-70 pointer-events-none"
                style={{
                    top: `30%`,
                    transform: "translateY(-20%)",
                }}
            >
                <img
                    src="/abstract1.webp"
                    alt="abstract left 1"
                    className="w-[500px] h-[500px] object-contain"
                    style={{ filter: "blur(0.5px)" }}
                />
            </div>
        )} */}

        {/* Right side images - always show first, second only if data is present, adjust position if no data */}
        {/* <div
            key="right-img-0"
            className="absolute right-0 z-0 opacity-70 pointer-events-none"
            style={{
                top: editableRows.length > 0 ? `18%` : `40%`,
                transform: "translateY(-20%)",
            }}
        >
            <img
                src="/abstract2.webp"
                alt="abstract right 0"
                className="w-[500px] h-[500px] object-contain"
                style={{ filter: "blur(0.5px)" }}
            />
        </div>
        {editableRows.length > 0 && (
            <div
                key="right-img-1"
                className="absolute right-0 z-0 opacity-70 pointer-events-none"
                style={{
                    top: `44%`,
                    transform: "translateY(-20%)",
                }}
            >
                <img
                    src="/abstract2.webp"
                    alt="abstract right 1"
                    className="w-[500px] h-[500px] object-contain"
                    style={{ filter: "blur(0.5px)" }}
                />
            </div>
        )} */}

    <div className="mx-auto max-w-7xl space-y-8">
        {/* Down Arrow Button (same style as up arrow, but vice-versa) */}
        {editableRows.length > 0 && !isSummaryInView && !showUpArrow && (
            <button
                onClick={() =>
                    summaryRef.current &&
                    summaryRef.current.scrollIntoView({ behavior: "smooth", block: "start" })
                }
                className="fixed bottom-8 left-1/2 transform -translate-x-1/2 z-50 
                             bg-white rounded-full shadow-lg p-3 flex items-center justify-center 
                             hover:bg-[#E4E1F0] transition-colors"
                style={{ border: "1px solid #615FA6" }}
                aria-label="Scroll to summary"
            >
                <svg
                    width="32"
                    height="32"
                    viewBox="0 0 24 24"
                    fill="none"
                    xmlns="http://www.w3.org/2000/svg"
                >
                    <path
                        d="M12 5v14M12 19l-7-7M12 19l7-7"
                        stroke="#615FA6"
                        strokeWidth="2.5"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                    />
                </svg>
            </button>
        )}

        {/* Main Form Card */}
        <Card className="bg-white/5 backdrop-blur border border-white/10 hover:bg-white/10 max-w-4xl mx-auto p-15">
            {/* <CardHeader className="text-center pb-8">
                <div
                    className="w-20 h-20 rounded-full flex items-center justify-center shadow-2xl mx-auto  mb-4"
                    style={{
                        background: "linear-gradient(130deg, #E6ECFF, #DFE4FF, #D3D6FE)",
                    }}
                >
                    <Sparkles className="h-10 w-10 text-[#615FA6]" />
                </div>
                <h1 className="text-4xl font-bold tracking-tight" style={{ color: "#615FA6" }}>
                    L <span style={{ color: "#D77E7B" }}>I</span> M A
                </h1>
                <CardDescription
                    className="text-base max-w-lg mx-auto"
                    style={{ color: "#615FA6" }}
                >
                    Enter your company credentials to fetch and process PLMaster mapping data from your backend system.
                </CardDescription>
            </CardHeader> */}

            <CardContent className="space-y-8">
                {/* Input Fields */}
                {/* <div className="grid md:grid-cols-2 gap-6">
                    <div className="space-y-3">
                        <label className="text-sm font-medium text-foreground flex items-center gap-2">
                            <div className="w-2 h-2 bg-[#615FA6] rounded-full"></div>
                            Company Code
                        </label>
                        <div className="relative group">
                            <input
                                type="text"
                                placeholder="Enter your company code"
                                value={sqlCompanyCode}
                                onChange={e => setSqlCompanyCode(e.target.value)}
                                className="w-full px-4 py-3 border border-border rounded-xl text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all duration-300 group-hover:border-primary/50"
                                style={{ background: "#DDE5FD" }}
                            />
                            <div className="absolute inset-y-0 right-3 flex items-center">
                                <Users className="h-4 w-4 text-muted-foreground" />
                            </div>
                        </div>
                    </div>

                    <div className="space-y-3">
                        <label className="text-sm font-medium text-foreground flex items-center gap-2">
                            <div className="w-2 h-2 bg-[#615FA6] rounded-full"></div>
                            Username
                        </label>
                        <div className="relative group">
                            <input
                                type="text"
                                placeholder="Enter your username"
                                value={sqlUsername}
                                onChange={e => setSqlUsername(e.target.value)}
                                className="w-full px-4 py-3 border border-border rounded-xl text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all duration-300 group-hover:border-primary/50"
                                style={{ background: "#DDE5FD" }}
                            />
                            <div className="absolute inset-y-0 right-3 flex items-center">
                                <FileText className="h-4 w-4 text-muted-foreground" />
                            </div>
                        </div>
                    </div>
                </div> */}
                {/* Display the received values for debugging/UX (optional) */}
                {/* <div className="grid md:grid-cols-2 gap-6">
                <div className="space-y-3">
                    <label className="text-sm font-medium text-foreground flex items-center gap-2">
                    <div className="w-2 h-2 bg-[#615FA6] rounded-full"></div>
                    Company Code (from iframe)
                    </label>
                    <div className="relative group">
                    <input
                        type="text"
                        readOnly
                        value={sqlCompanyCode}
                        className="w-full px-4 py-3 border border-border rounded-xl text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all duration-300 group-hover:border-primary/50"
                        style={{ background: "#DDE5FD" }}
                    />
                    </div>
                </div>
                <div className="space-y-3">
                    <label className="text-sm font-medium text-foreground flex items-center gap-2">
                    <div className="w-2 h-2 bg-[#615FA6] rounded-full"></div>
                    Username (from iframe)
                    </label>
                    <div className="relative group">
                    <input
                        type="text"
                        readOnly
                        value={sqlUsername}
                        className="w-full px-4 py-3 border border-border rounded-xl text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all duration-300 group-hover:border-primary/50"
                        style={{ background: "#DDE5FD" }}
                    />
                    </div>
                </div>
                </div> */}

                {/* Action Button */}
                <div className="flex justify-center pt-4 gap-4">
                    <Button
                        onClick={handleSqlMapping}
                        disabled={sqlLoading || !sqlCompanyCode || !sqlUsername}
                        size="lg"
                        className="px-8 py-3 font-semibold rounded-xl shadow-glow hover:shadow-large transition-all duration-300 disabled:opacity-50 disabled:cursor-not-allowed hover-lift"
                        style={{
                            background: "linear-gradient(to bottom, #E1A357 0%, #D5807B 100%)",
                            color: "#fff",
                            border: "none",
                        }}
                    >
                        {sqlLoading ? (
                            <span className="flex items-center gap-2">
                                <Loader2 className="h-5 w-5 animate-spin" />
                                Processing Your Data...
                            </span>
                        ) : (
                            <span className="flex items-center gap-3 ">
                                <Database className="h-5 w-5" />
                                Get Lineitem Mapping
                            </span>
                        )}
                    </Button>
                    {/* Download Section */}
                    {editableRows.length > 0 && (
                        <Button
                            variant="outline"
                            disabled={saving}
                            onClick={async () => {
                                if (editableRows.length === 0) return;
                                setSaving(true);
                                // Use the same column order as finalCsv
                                const csvHeaders = [
                                    "Id",
                                    "CompanyCode",
                                    "GLCode",
                                    "LineItem",
                                    "GrandParent",
                                    "Parent",
                                    "UpdatedOn",
                                    "UpdatedBy",
                                ];
                                const csvRows = editableRows.map(row =>
                                    csvHeaders.map(h => {
                                        if (h === "LineItem") return row.line_item ?? "";
                                        if (h === "Parent") return row.parent ?? "";
                                        if (h === "GrandParent") return row.grandparent ?? "";
                                        return row[h] ?? "";
                                    })
                                );
                                const csvString = [
                                    csvHeaders.join(","),
                                    ...csvRows.map(r =>
                                        r.map(v => (v ?? "").toString().replace(/\r|\n|,/g, " ")).join(",")
                                    ),
                                ].join("\n");
                                // Parse CSV to rows for backend
                                const rows = editableRows.map(row => {
                                    const obj: any = {};
                                    csvHeaders.forEach(h => {
                                        if (h === "LineItem") obj[h] = row.line_item ?? "";
                                        else if (h === "Parent") obj[h] = row.parent ?? "";
                                        else if (h === "GrandParent") obj[h] = row.grandparent ?? "";
                                        else obj[h] = row[h] ?? "";
                                    });
                                    return obj;
                                });
                                try {
                                    // 1. Store in SQL
                                    await axios.post(`${API_BASE}/glmapapi/store_auto_mapping`, { rows });
                                    // 2. Save edited lineitem/parent/grandparent to company CSV and build artifacts
                                    const saveRows = editableRows.map(row => ({
                                        line_item: row.line_item ?? "",
                                        parent: row.parent ?? "",
                                        grandparent: row.grandparent ?? "",
                                    }));
                                    await axios.post(`${API_BASE}/glmapapi/save`, {
                                        company_code: sqlCompanyCode,
                                        rows: saveRows,
                                    });
                                    // 3. Download CSV after storing
                                    const blob = new Blob([csvString], {
                                        type: "text/csv;charset=utf-8;",
                                    });
                                    const url = URL.createObjectURL(blob);
                                    const link = document.createElement("a");
                                    link.href = url;
                                    link.download = `pl_master_map_${sqlCompanyCode}_${new Date()
                                        .toISOString()
                                        .split("T")[0]}.csv`;
                                    document.body.appendChild(link);
                                    link.click();
                                    document.body.removeChild(link);

                                    toast({
                                        title: "Success!",
                                        description: "Data saved and CSV downloaded successfully.",
                                        variant: "default",
                                    });
                                } catch (e: any) {
                                    toast({
                                        title: "Error",
                                        description: `Failed to store auto mapping or save company CSV: ${e?.response?.data?.detail || e?.message || e}`,
                                        variant: "destructive",
                                    });
                                } finally {
                                    setSaving(false);
                                }
                            }}
                            size="lg"
                            className="px-8 py-3 font-semibold rounded-xl shadow-glow hover:shadow-large transition-all duration-300 disabled:opacity-50 disabled:cursor-not-allowed hover-lift"
                            style={{
                                background: "linear-gradient(to bottom, #E1A357 0%, #D5807B 100%)",
                                color: "#fff",
                                border: "none",
                            }}
                        >
                            {saving ? (
                                <span className="flex items-center gap-2">
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                    Saving...
                                </span>
                            ) : (
                                <span className="flex items-center gap-2">
                                    <Download className="h-5 w-5" />
                                    Save & Download
                                </span>
                            )}
                        </Button>
                    )}
                </div>
            </CardContent>
        </Card>

        {/* Results Section */}
        {editableRows.length > 0 && (
            <div ref={summaryRef} className="space-y-6 animate-slide-up ">
                {/* Up Arrow Button */}
                {showUpArrow && (
                    <button
                        onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
                        className="fixed bottom-8 right-8 z-50 bg-white rounded-full shadow-lg p-3 flex items-center justify-center hover:bg-[#E4E1F0] transition-colors"
                        style={{ border: "1px solid #615FA6" }}
                        aria-label="Scroll to top"
                    >
                        <svg
                            width="32"
                            height="32"
                            viewBox="0 0 24 24"
                            fill="none"
                            xmlns="http://www.w3.org/2000/svg"
                        >
                            <path
                                d="M12 19V5M12 5L5 12M12 5L19 12"
                                stroke="#615FA6"
                                strokeWidth="2.5"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                            />
                        </svg>
                    </button>
                )}
                {/* Summary Cards */}
                {summaryCounts && (
                    <Card className="bg-white/20 backdrop-blur border border-white/10 shadow-md">
                        <CardHeader>
                            <CardTitle className="flex items-center gap-2">
                                <TrendingUp className="h-5 w-5 text-primary" />
                                Processing Summary
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                <div className="p-6 rounded-2xl text-center hover-lift bg-white/20 backdrop-blur border border-white/10">
                                    <div className="text-3xl font-bold text-blue-700 mb-2">
                                        {summaryCounts.total.toLocaleString()}
                                    </div>
                                    <div className="text-sm text-blue-600 font-medium">Total Items</div>
                                </div>
                                <div className="p-6 rounded-2xl text-center hover-lift bg-white/20 backdrop-blur border border-white/10">
                                    <div className="text-3xl font-bold text-green-700 mb-2">
                                        {summaryCounts.mapped_existing.toLocaleString()}
                                    </div>
                                    <div className="text-sm text-green-600 font-medium">Existing</div>
                                </div>
                                <div className="p-6 rounded-2xl text-center hover-lift bg-white/20 backdrop-blur border border-white/10">
                                    <div className="text-3xl font-bold text-yellow-700 mb-2">
                                        {summaryCounts.predicted.toLocaleString()}
                                    </div>
                                    <div className="text-sm text-yellow-600 font-medium">Predicted</div>
                                </div>
                                <div className="p-6 rounded-2xl text-center hover-lift bg-white/20 backdrop-blur border border-white/10">
                                    <div className="text-3xl font-bold text-purple-700 mb-2">
                                        {(summaryCounts.mapped_percent * 100).toFixed(1)}%
                                    </div>
                                    <div className="text-sm text-purple-600 font-medium">Coverage</div>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                )}

                {/* Data Table */}
                <Card className="shadow-md bg-white/20 backdrop-blur border border-white/10">
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <BarChart3 className="h-5 w-5 text-primary" />
                            Tabulated Data
                        </CardTitle>
                        <CardDescription>
                            Review and edit the AI predictions below. You can modify Parent or GrandParent values before saving.
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="rounded-2xl border border-border/100 overflow-hidden bg-surface-elevated">
                            <Table>
                                <TableHeader>
                                    <TableRow className="bg-accent-soft/150 hover:bg-accent-soft/100">
                                        <TableHead className="font-semibold text-foreground py-4 w-32">
                                            Line Item
                                        </TableHead>
                                        <TableHead className="font-semibold text-foreground py-4 ">
                                            Grand Parent
                                        </TableHead>
                                        <TableHead className="font-semibold text-foreground py-4 ">
                                            Parent
                                        </TableHead>
                                        <TableHead className="font-semibold text-foreground py-4">
                                            Source
                                        </TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {paginatedRows.map((row, idx) => (
                                        <TableRow
                                            key={idx + (currentPage - 1) * ITEMS_PER_PAGE}
                                            className="hover:bg-accent-soft/30 transition-colors duration-200"
                                        >
                                            <TableCell className="font-medium py-4 text-foreground w-32 truncate">
                                                {row.line_item}
                                            </TableCell>
                                            <TableCell className="py-4 pl-2">
                                                <input
                                                    type="text"
                                                    value={row.grandparent}
                                                    onChange={e =>
                                                        handleEditCell(
                                                            idx + (currentPage - 1) * ITEMS_PER_PAGE,
                                                            "grandparent",
                                                            e.target.value
                                                        )
                                                    }
                                                    className="w-full px-3 py-2 border border-blue-200 rounded-lg text-blue-900 focus:outline-none focus:ring-2 focus:ring-blue-200/50 focus:border-blue-400 transition-all duration-200"
                                                    style={{ background: "#DDE5FD" }}
                                                />
                                            </TableCell>
                                            <TableCell className="py-4 pl-2">
                                                <input
                                                    type="text"
                                                    value={row.parent}
                                                    onChange={e =>
                                                        handleEditCell(
                                                            idx + (currentPage - 1) * ITEMS_PER_PAGE,
                                                            "parent",
                                                            e.target.value
                                                        )
                                                    }
                                                    className="w-full px-3 py-2 border border-purple-200 rounded-lg text-purple-900 focus:outline-none focus:ring-2 focus:ring-purple-200/50 focus:border-purple-400 transition-all duration-200"
                                                    style={{ background: "#DDE5FD" }}
                                                />
                                            </TableCell>
                                            <TableCell className="py-4">
                                                <span
                                                    className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-medium ${
                                                        row.source === "existing"
                                                            ? "bg-green-100 text-green-700 border border-green-200"
                                                            : "bg-yellow-100 text-yellow-700 border border-yellow-200"
                                                    }`}
                                                >
                                                    {row.source === "existing" ? "Existing" : "Predicted"}
                                                </span>
                                            </TableCell>
                                        </TableRow>
                                    ))}
                                </TableBody>
                            </Table>
                        </div>

                        {/* Enhanced Pagination */}
                        {totalPages > 1 && (
                            <div className="mt-8 flex justify-center">
                                <div className="bg-surface-elevated rounded-2xl p-2 shadow-medium">
                                    <Pagination>
                                        <PaginationContent className="gap-2">
                                            <PaginationItem>
                                                <PaginationPrevious
                                                    onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
                                                    className={`rounded-xl transition-all duration-200 ${
                                                        currentPage <= 1
                                                            ? "pointer-events-none opacity-50"
                                                            : "cursor-pointer hover:bg-primary/10 hover:text-primary"
                                                    }`}
                                                />
                                            </PaginationItem>
                                            {[...Array(Math.min(5, totalPages))].map((_, i) => {
                                                const pageNum = i + Math.max(1, currentPage - 2);
                                                if (pageNum > totalPages) return null;
                                                return (
                                                    <PaginationItem key={pageNum}>
                                                        <PaginationLink
                                                            onClick={() => setCurrentPage(pageNum)}
                                                            isActive={currentPage === pageNum}
                                                            className={`rounded-xl cursor-pointer transition-all duration-200 ${
                                                                currentPage === pageNum
                                                                    ? "bg-[#615FA6] text-primary-foreground shadow-glow"
                                                                    : "hover:bg-[#615FA6]/10 hover:text-primary"
                                                            }`}
                                                        >
                                                            {pageNum}
                                                        </PaginationLink>
                                                    </PaginationItem>
                                                );
                                            })}
                                            <PaginationItem>
                                                <PaginationNext
                                                    onClick={() =>
                                                        setCurrentPage(Math.min(totalPages, currentPage + 1))
                                                    }
                                                    className={`rounded-xl transition-all duration-200 ${
                                                        currentPage >= totalPages
                                                            ? "pointer-events-none opacity-50"
                                                            : "cursor-pointer hover:bg-primary/10 hover:text-primary"
                                                    }`}
                                                />
                                            </PaginationItem>
                                        </PaginationContent>
                                    </Pagination>
                                </div>
                            </div>
                        )}
                    </CardContent>
                    {/* Download Section */}
                {editableRows.length > 0 && (
                    <div className="m-6 pt-3 border-t border-border/50">
                        <div className="flex items-center justify-between">
                            <div className="space-y-1">
                                <h3 className="font-semibold text-foreground">Ready to Export</h3>
                                <p className="text-sm text-muted-foreground">
                                    Save your processed data and download the CSV file
                                </p>
                            </div>
                            <Button
                                variant="outline"
                                disabled={saving}
                                onClick={async () => {
                                    if (editableRows.length === 0) return;
                                    setSaving(true);
                                    // Use the same column order as finalCsv
                                    const csvHeaders = [
                                        "Id",
                                        "CompanyCode",
                                        "GLCode",
                                        "LineItem",
                                        "GrandParent",
                                        "Parent",
                                        "UpdatedOn",
                                        "UpdatedBy",
                                    ];
                                    const csvRows = editableRows.map(row =>
                                        csvHeaders.map(h => {
                                            if (h === "LineItem") return row.line_item ?? "";
                                            if (h === "Parent") return row.parent ?? "";
                                            if (h === "GrandParent") return row.grandparent ?? "";
                                            return row[h] ?? "";
                                        })
                                    );
                                    const csvString = [
                                        csvHeaders.join(","),
                                        ...csvRows.map(r =>
                                            r.map(v => (v ?? "").toString().replace(/\r|\n|,/g, " ")).join(",")
                                        ),
                                    ].join("\n");
                                    // Parse CSV to rows for backend
                                    const rows = editableRows.map(row => {
                                        const obj: any = {};
                                        csvHeaders.forEach(h => {
                                            if (h === "LineItem") obj[h] = row.line_item ?? "";
                                            else if (h === "Parent") obj[h] = row.parent ?? "";
                                            else if (h === "GrandParent") obj[h] = row.grandparent ?? "";
                                            else obj[h] = row[h] ?? "";
                                        });
                                        return obj;
                                    });
                                    try {
                                        // 1. Store in SQL
                                        await axios.post(`${API_BASE}/glmapapi/store_auto_mapping`, { rows });
                                        // 2. Save edited lineitem/parent/grandparent to company CSV and build artifacts
                                        const saveRows = editableRows.map(row => ({
                                            line_item: row.line_item ?? "",
                                            parent: row.parent ?? "",
                                            grandparent: row.grandparent ?? "",
                                        }));
                                        await axios.post(`${API_BASE}/glmapapi/save`, {
                                            company_code: sqlCompanyCode,
                                            rows: saveRows,
                                        });
                                        // 3. Download CSV after storing
                                        const blob = new Blob([csvString], {
                                            type: "text/csv;charset=utf-8;",
                                        });
                                        const url = URL.createObjectURL(blob);
                                        const link = document.createElement("a");
                                        link.href = url;
                                        link.download = `pl_master_map_${sqlCompanyCode}_${new Date()
                                            .toISOString()
                                            .split("T")[0]}.csv`;
                                        document.body.appendChild(link);
                                        link.click();
                                        document.body.removeChild(link);

                                        toast({
                                            title: "Success!",
                                            description: "Data saved and CSV downloaded successfully.",
                                            variant: "default",
                                        });
                                    } catch (e: any) {
                                        toast({
                                            title: "Error",
                                            description: `Failed to store auto mapping or save company CSV: ${e?.response?.data?.detail || e?.message || e}`,
                                            variant: "destructive",
                                        });
                                    } finally {
                                        setSaving(false);
                                    }
                                }}
                                className="px-6 py-2 hover-lift"
                                style={{
                                    background: "linear-gradient(to bottom, #E1A357 0%, #D5807B 100%)",
                                    color: "#fff",
                                    border: "none",
                                }}
                            >
                                {saving ? (
                                    <span className="flex items-center gap-2">
                                        <Loader2 className="h-4 w-4 animate-spin" />
                                        Saving...
                                    </span>
                                ) : (
                                    <span className="flex items-center gap-2">
                                        <Download className="h-4 w-4" />
                                        Save & Download
                                    </span>
                                )}
                            </Button>
                        </div>
                    </div>
                )}
                </Card>
            </div>
        )}
    </div>
</div>
  );
};

export default SqlPlMasterMapping;