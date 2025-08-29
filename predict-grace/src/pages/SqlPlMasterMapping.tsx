import React, { useState, useMemo } from "react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Pagination, PaginationContent, PaginationItem, PaginationLink, PaginationNext, PaginationPrevious } from "@/components/ui/pagination";
import { BarChart3, Database, Download, Loader2 } from "lucide-react";

import { useToast } from "@/hooks/use-toast";
import axios from "axios";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

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
  const ITEMS_PER_PAGE = 20;

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

  // Use finalCsv to display the table
  React.useEffect(() => {
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
        // For display, use consistent keys
        rowObj.line_item = rowObj.LineItem ?? rowObj.line_item ?? "";
        rowObj.parent = rowObj.Parent ?? rowObj.parent ?? "";
        rowObj.grandparent = rowObj.GrandParent ?? rowObj.grandparent ?? "";
        rowObj.source = "finalCsv";
        rows.push(rowObj);
      }
      setEditableRows(rows);
    } else {
      setEditableRows([]);
    }
  }, [finalCsv]);

  const handleEditCell = (rowIdx: number, field: string, value: string) => {
    setEditableRows(prev => prev.map((row, idx) => idx === rowIdx ? { ...row, [field]: value } : row));
  };

  const handleSqlMapping = async () => {
    if (!sqlCompanyCode || !sqlUsername) {
      alert("Please enter both companycode and username.");
      return;
    }
    setSqlLoading(true);
    try {
      const resp = await axios.post(`${API_BASE}/get_plmaster_mapping`, {
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
    <div className="min-h-screen bg-background p-6">
      <div className="mx-auto max-w-5xl space-y-8 flex flex-col items-center">
        <Card className="bg-surface-elevated w-full max-w-5xl">
          <CardHeader className="flex flex-row items-center justify-between">
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-3">
                {/* Database Lucide icon */}
                <Database className="h-6 w-6 text-primary " />
                
                <CardTitle className="text-2xl font-bold">L I M A</CardTitle>
                </div>
              <div className="flex items-center gap-2 text-muted-foreground">
                <span className="text-sm">&#10024; Line Item Mapping AI</span>
              </div>
              <CardDescription className="mt-2">Enter your company credentials below to fetch and process PLMaster mapping data from the backend system.</CardDescription>
            </div>
            <Button variant="outline" onClick={() => window.location.href = '/index'} className="ml-auto">
              Lineitem Processor
            </Button>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col sm:flex-row gap-8 items-center mt-2">
              <div className="flex flex-col gap-2 w-full sm:w-1/2">
                <label className="font-semibold text-sm text-muted-foreground flex items-center gap-2">
                  {/* Company icon */}
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor"><rect x="3" y="7" width="18" height="13" rx="2"/><rect x="7" y="3" width="10" height="4" rx="1"/></svg>
                  Company Code
                </label>
                <input
                  type="text"
                  placeholder="Enter company code"
                  value={sqlCompanyCode}
                  onChange={e => setSqlCompanyCode(e.target.value)}
                  className="px-3 py-2 border rounded-md text-sm bg-background"
                />
              </div>
              <div className="flex flex-col gap-2 w-full sm:w-1/2">
                <label className="font-semibold text-sm text-muted-foreground flex items-center gap-2">
                  {/* User icon */}
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 4-6 8-6s8 2 8 6"/></svg>
                  Username
                </label>
                <input
                  type="text"
                  placeholder="Enter username"
                  value={sqlUsername}
                  onChange={e => setSqlUsername(e.target.value)}
                  className="px-3 py-2 border rounded-md text-sm bg-background"
                />
              </div>
            </div>
            <div className="flex justify-center mt-6">
            <Button
                onClick={handleSqlMapping}
                disabled={sqlLoading}
                className="px-6 py-2 text-base font-semibold"
            >
                {sqlLoading ? (
                <span className="flex items-center gap-2">
                    <Loader2 className="h-5 w-5 animate-spin text-white" />
                    Processing...
                </span>
                ) : (
                <span className="flex items-center gap-3">
                    <Database className="h-5 w-5" />
                    Get PLMaster Mapping
                </span>
                )}
            </Button>
            </div>
            {/* Download Final CSV Button */}
            {editableRows.length > 0 && (
              <div className="mt-4 flex justify-end">
                <Button
                  variant="outline"
                  disabled={saving}
                  onClick={async () => {
                    if (editableRows.length === 0) return;
                    setSaving(true);
                    // Use the same column order as finalCsv
                    const csvHeaders = ["Id", "CompanyCode", "GLCode", "LineItem", "GrandParent", "Parent", "UpdatedOn", "UpdatedBy"];
                    const csvRows = editableRows.map(row =>
                      csvHeaders.map(h => {
                        if (h === "LineItem") return row.line_item ?? "";
                        if (h === "Parent") return row.parent ?? "";
                        if (h === "GrandParent") return row.grandparent ?? "";
                        return row[h] ?? "";
                      })
                    );
                    const csvString = [csvHeaders.join(","), ...csvRows.map(r => r.map(v => (v ?? "").toString().replace(/\r|\n|,/g, " ")).join(","))].join("\n");
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
                      await axios.post(`${API_BASE}/store_auto_mapping`, { rows });
                      // 2. Save edited lineitem/parent/grandparent to company CSV and build artifacts
                      const saveRows = editableRows.map(row => ({
                        line_item: row.line_item ?? "",
                        parent: row.parent ?? "",
                        grandparent: row.grandparent ?? ""
                      }));
                      await axios.post(`${API_BASE}/save`, {
                        company_code: sqlCompanyCode,
                        rows: saveRows
                      });
                      // 3. Download CSV after storing
                      const blob = new Blob([csvString], { type: "text/csv;charset=utf-8;" });
                      const url = URL.createObjectURL(blob);
                      const link = document.createElement("a");
                      link.href = url;
                      link.download = `final_plmaster_mapping_${new Date().toISOString().split("T")[0]}.csv`;
                      document.body.appendChild(link);
                      link.click();
                      document.body.removeChild(link);
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
                >
                  {saving ? (
                    <span className="flex items-center gap-2">
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Saving...
                    </span>
                  ) : (
                    <span className="flex items-center gap-2">
                      <Download className="mr-2 h-4 w-4" />
                      Save & Download
                    </span>
                  )}
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Editable LangExtract Table UI with summary above */}
        {editableRows.length > 0 && (
          <div className="w-full max-w-7xl mt-8">
            {/* Processing Summary above the table */}
            {summaryCounts && (
              <Card className="bg-surface-elevated mb-4">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <BarChart3 className="h-5 w-5" />
                    Processing Summary
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
                    <div className="text-center p-4 bg-accent-soft rounded-lg">
                      <div className="text-2xl font-bold text-foreground">{summaryCounts.total}</div>
                      <div className="text-sm text-muted-foreground">Total Items</div>
                    </div>
                    <div className="text-center p-4 bg-accent-soft rounded-lg">
                      <div className="text-2xl font-bold text-success">{summaryCounts.mapped_existing}</div>
                      <div className="text-sm text-muted-foreground">Existing</div>
                    </div>
                    <div className="text-center p-4 bg-accent-soft rounded-lg">
                      <div className="text-2xl font-bold text-warning">{summaryCounts.predicted}</div>
                      <div className="text-sm text-muted-foreground">Predicted</div>
                    </div>
                    <div className="text-center p-4 bg-accent-soft rounded-lg">
                      <div className="text-2xl font-bold text-foreground">{(summaryCounts.mapped_percent * 100).toFixed(1)}%</div>
                      <div className="text-sm text-muted-foreground">Coverage</div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}
            <Card className="bg-surface-elevated">
              <CardHeader>
                <CardTitle>Tabulated Data</CardTitle>
                <CardDescription>
                  Edit the predicted results below. You can change Parent or GrandParent values before saving.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="rounded-md border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Line Item</TableHead>
                        <TableHead>Grand Parent</TableHead>
                        <TableHead>Parent</TableHead>
                        <TableHead>Source</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {paginatedRows.map((row, idx) => (
                        <TableRow key={idx + (currentPage - 1) * ITEMS_PER_PAGE}>
                          <TableCell className="font-medium">{row.line_item}</TableCell>
                          <TableCell>
                            <input
                              type="text"
                              value={row.grandparent}
                              onChange={e => handleEditCell(idx + (currentPage - 1) * ITEMS_PER_PAGE, "grandparent", e.target.value)}
                              className="px-2 py-1 border rounded w-full"
                            />
                          </TableCell>
                          <TableCell>
                            <input
                              type="text"
                              value={row.parent}
                              onChange={e => handleEditCell(idx + (currentPage - 1) * ITEMS_PER_PAGE, "parent", e.target.value)}
                              className="px-2 py-1 border rounded w-full"
                            />
                          </TableCell>
                          <TableCell>
                            <span className={row.source === "existing" ? "bg-success text-success-foreground px-2 py-1 rounded" : "bg-warning text-warning-foreground px-2 py-1 rounded"}>
                              {row.source === "existing" ? "Existing" : "Predicted"}
                            </span>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>

                {/* Pagination Controls - same as Index.tsx */}
                {totalPages > 1 && (
                  <div className="mt-4">
                    <Pagination>
                      <PaginationContent>
                        <PaginationItem>
                          <PaginationPrevious 
                            onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
                            className={currentPage <= 1 ? "pointer-events-none opacity-50" : "cursor-pointer"}
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
                                className="cursor-pointer"
                              >
                                {pageNum}
                              </PaginationLink>
                            </PaginationItem>
                          );
                        })}
                        <PaginationItem>
                          <PaginationNext 
                            onClick={() => setCurrentPage(Math.min(totalPages, currentPage + 1))}
                            className={currentPage >= totalPages ? "pointer-events-none opacity-50" : "cursor-pointer"}
                          />
                        </PaginationItem>
                      </PaginationContent>
                    </Pagination>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </div>
  );
};

export default SqlPlMasterMapping;
