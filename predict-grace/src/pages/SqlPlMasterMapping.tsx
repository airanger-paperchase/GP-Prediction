import React, { useState, useMemo } from "react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Pagination, PaginationContent, PaginationItem, PaginationLink, PaginationNext, PaginationPrevious } from "@/components/ui/pagination";
import { useToast } from "@/hooks/use-toast";
import axios from "axios";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

const SqlPlMasterMapping: React.FC = () => {
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
            <div>
              <CardTitle>SQL PLMaster Mapping</CardTitle>
              <CardDescription>Enter companycode and username, then click to fetch mapping from backend.</CardDescription>
            </div>
            <Button variant="outline" onClick={() => window.location.href = '/index'} className="ml-auto">
              Go to LineItem Processor
            </Button>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col sm:flex-row gap-2 items-center">
              <input
                type="text"
                placeholder="Company Code"
                value={sqlCompanyCode}
                onChange={e => setSqlCompanyCode(e.target.value)}
                className="px-3 py-2 border rounded-md text-sm"
                style={{ minWidth: 120 }}
              />
              <input
                type="text"
                placeholder="Username"
                value={sqlUsername}
                onChange={e => setSqlUsername(e.target.value)}
                className="px-3 py-2 border rounded-md text-sm"
                style={{ minWidth: 120 }}
              />
              <Button onClick={handleSqlMapping} disabled={sqlLoading} className="w-full sm:w-auto">
                {sqlLoading ? "Processing..." : "Get PLMaster Mapping"}
              </Button>
            </div>
            {/* Download Final CSV Button */}
            {editableRows.length > 0 && (
              <div className="mt-4 flex justify-end">
                <Button
                  variant="outline"
                  onClick={async () => {
                    // Rebuild CSV from editableRows
                    if (editableRows.length === 0) return;
                    // Use the same column order as finalCsv
                    const csvHeaders = ["Id", "CompanyCode", "GLCode", "LineItem", "GrandParent", "Parent", "UpdatedOn", "UpdatedBy"];
                    const csvRows = editableRows.map(row =>
                      csvHeaders.map(h => {
                        // Map keys to match header
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
                      await axios.post(`${API_BASE}/store_auto_mapping`, { rows });
                      // Download CSV after storing
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
                        description: `Failed to store auto mapping: ${e?.response?.data?.detail || e?.message || e}`,
                        variant: "destructive",
                      });
                    }
                  }}
                >
                  Download Final Mapping CSV
                </Button>
              </div>
            )}
            
          </CardContent>
        </Card>

        {/* Editable LangExtract Table UI */}
        {editableRows.length > 0 && (
          <Card className="bg-surface-elevated mt-8 w-full max-w-7xl">
            <CardHeader>
              <CardTitle>LangExtract Results (Editable)</CardTitle>
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
        )}
      </div>
    </div>
  );
};

export default SqlPlMasterMapping;
