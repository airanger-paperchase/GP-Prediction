import React, { useMemo, useState } from "react";
import { useToast } from "@/hooks/use-toast";
import axios from "axios";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Pagination, PaginationContent, PaginationItem, PaginationLink, PaginationNext, PaginationPrevious } from "@/components/ui/pagination";
import { Progress } from "@/components/ui/progress";
import { Upload, Download, Save, FileText, BarChart3 } from "lucide-react";

type Row = {
  line_item: string;
  parent: string;
  grandparent: string;
  parent_confidence?: number;
  grandparent_confidence?: number;
  source?: "existing" | "predicted";
};

type PredictResponse = {
  company_code: string;
  counts: { total: number; mapped_existing: number; predicted: number; mapped_percent: number };
  rows: Row[];
  full_dataset?: Row[];
};

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";
const ITEMS_PER_PAGE = 20;

const Index = () => {
  const { toast } = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<PredictResponse | null>(null);
  const [saving, setSaving] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);

  const rows = useMemo(() => data?.full_dataset || data?.rows || [], [data]);
  
  const totalPages = Math.ceil(rows.length / ITEMS_PER_PAGE);
  const paginatedRows = useMemo(() => {
    const startIndex = (currentPage - 1) * ITEMS_PER_PAGE;
    return rows.slice(startIndex, startIndex + ITEMS_PER_PAGE);
  }, [rows, currentPage]);

  const handlePredict = async () => {
    if (!file) {
      alert("Please choose a CSV/XLSX file to upload.");
      return;
    }

    setLoading(true);
    setData(null);
    setCurrentPage(1);

    try {
      const form = new FormData();
      form.append("file", file);

      const upResp = await axios.post<{
        company_code: string;
        missing_lineitems?: string[];
        premapped_rows?: Array<{ line_item: string; parent: string; grandparent: string; row_index?: number }>;
        partial_rows?: any[];
        counts?: any;
      }>(`${API_BASE}/upload/extract_missing`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });

      const company_code = upResp.data.company_code;
      // If no company code in file, show input
      if (!company_code) {
        setShowCompanyCodeInput(true);
      } else {
        setShowCompanyCodeInput(false);
        setManualCompanyCode(company_code);
      }
      const missing = upResp.data.missing_lineitems || [];
      const premapped = upResp.data.premapped_rows || [];

      if (!company_code) {
        alert("Upload returned no company_code.");
        setLoading(false);
        return;
      }

      let predictedRows: Row[] = [];
      if (missing.length > 0) {
        const leReq = { company_code, lines: missing };
        const leResp = await axios.post(`${API_BASE}/batch/langextract_by_company`, leReq);
        const backend = leResp.data as any;
        const results = backend.results || backend.Results || [];

        predictedRows = (results || []).map((r: any) => ({
          line_item: r.line_item ?? r.normalized ?? "",
          parent: r.parent ?? "",
          grandparent: r.grandparent ?? "",
          parent_confidence: typeof r.parent_confidence === "number" ? r.parent_confidence : undefined,
          grandparent_confidence: typeof r.grandparent_confidence === "number" ? r.grandparent_confidence : undefined,
          source: "predicted",
        }));
      }

      const premappedRowsMapped: Row[] = premapped.map((p) => ({
        line_item: p.line_item || "",
        parent: p.parent || "",
        grandparent: p.grandparent || "",
        source: "existing",
      }));

      const fullDataset: Row[] = [...premappedRowsMapped, ...predictedRows];

      const counts = {
        total: fullDataset.length,
        mapped_existing: premappedRowsMapped.length,
        predicted: predictedRows.length,
        mapped_percent: fullDataset.length > 0 ? premappedRowsMapped.length / fullDataset.length : 0,
      };

      setData({
        company_code,
        counts,
        rows: fullDataset,
        full_dataset: fullDataset,
      });
    } catch (e: any) {
      console.error(e);
      alert(`Predict failed: ${e?.response?.data?.detail || e?.message || e}`);
    } finally {
      setLoading(false);
    }
  };

  const [manualCompanyCode, setManualCompanyCode] = useState("");
  const [showCompanyCodeInput, setShowCompanyCodeInput] = useState(false);

  // Update the file upload section to include the company code input
  {showCompanyCodeInput && (
    <div className="mt-4">
      <label htmlFor="company-code" className="block text-sm font-medium text-muted-foreground mb-2">
        Company Code
      </label>
      <input
        id="company-code"
        type="text"
        value={manualCompanyCode}
        onChange={(e) => setManualCompanyCode(e.target.value)}
        placeholder="Enter company code"
        className="w-full px-3 py-2 border rounded-md text-sm"
        required
      />
    </div>
  )}

  const handleSave = async () => {
    if (!data) {
      alert("Nothing to save.");
      return;
    }
    
    const companyCodeToUse = manualCompanyCode || data.company_code;
    if (!companyCodeToUse) {
      alert("Please enter a company code.");
      return;
    }
  
    setSaving(true);
    try {
      const payload = {
        company_code: companyCodeToUse,
        rows: data.full_dataset || data.rows,
      };
  
      await axios.post(`${API_BASE}/save`, payload, {
        headers: { "Content-Type": "application/json" }
      });
  
      alert("Saved and artifacts built");
    } catch (e: any) {
      console.error(e);
      alert(`Save failed: ${e?.response?.data?.detail || e.message || 'Unknown error'}`);
    } finally {
      setSaving(false);
    }
  };

  const handleDownloadCSV = async () => {
    if (!data) return;
    try {
      // Store to SQL before download
      await axios.post(`${API_BASE}/store_auto_mapping`, {
        rows: data.full_dataset || data.rows,
      });
    } catch (e: any) {
      toast({
        title: "Error",
        description: `Failed to store auto mapping: ${e?.response?.data?.detail || e?.message || e}`,
        variant: "destructive",
      });
      // Still allow download
    }
    const csvContent = [
      "LineItem,Parent,GrandParent",
      ...(data.full_dataset || data.rows).map((row) =>
        `"${(row.line_item || "").replace(/"/g, '""')}","${(row.parent || "").replace(/"/g, '""')}","${(row.grandparent || "").replace(/"/g, '""')}"`
      ),
    ].join("\n");

    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `predictions_${new Date().toISOString().split("T")[0]}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const counts = data?.counts;

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="mx-auto max-w-7xl space-y-8">
      <div className="text-center">
          <h1 className="text-3xl font-bold tracking-tight text-foreground mb-2">LineItem Processor</h1>
          <p className="text-lg text-muted-foreground">Upload your CSV/XLSX file to extract and predict line item mappings</p>
        </div>

        <Card className="bg-surface-elevated">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Upload className="h-5 w-5" />
              File Upload
            </CardTitle>
            <CardDescription>
              Select a CSV or XLSX file containing company data. The system will identify missing items and generate predictions.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center">
              <div className="flex-1">
                <input
                  type="file"
                  accept=".csv,.xlsx,.xls"
                  onChange={(e) => setFile(e.target.files?.[0] || null)}
                  className="w-full text-sm text-muted-foreground file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-medium file:bg-accent file:text-accent-foreground hover:file:bg-accent/80"
                />
              </div>
              <Button onClick={handlePredict} disabled={!file || loading} className="w-full sm:w-auto">
                {loading ? "Processing..." : "Upload & Predict"}
              </Button>
            </div>
            
            {loading && (
              <div className="mt-4">
                <Progress className="w-full" />
                <p className="text-sm text-muted-foreground mt-2">Processing your file...</p>
              </div>
            )}

            {file && (
              <div className="mt-4 flex items-center gap-2 text-sm text-muted-foreground">
                <FileText className="h-4 w-4" />
                Selected: {file.name} ({(file.size / 1024).toFixed(1)} KB)
              </div>
            )}
          </CardContent>
        </Card>

        {/* Link to SQL PLMaster Mapping Page */}
        <div className="flex justify-end mb-4">
          <a href="/SqlPlMasterMapping" className="underline text-primary hover:text-primary-dark">Go to SQL PLMaster Mapping</a>
        </div>
        

        {counts && (
          <Card className="bg-surface-elevated">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <BarChart3 className="h-5 w-5" />
                Processing Summary
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
                <div className="text-center p-4 bg-accent-soft rounded-lg">
                  <div className="text-2xl font-bold text-foreground">{counts.total}</div>
                  <div className="text-sm text-muted-foreground">Total Items</div>
                </div>
                <div className="text-center p-4 bg-accent-soft rounded-lg">
                  <div className="text-2xl font-bold text-success">{counts.mapped_existing}</div>
                  <div className="text-sm text-muted-foreground">Existing</div>
                </div>
                <div className="text-center p-4 bg-accent-soft rounded-lg">
                  <div className="text-2xl font-bold text-warning">{counts.predicted}</div>
                  <div className="text-sm text-muted-foreground">Predicted</div>
                </div>
                <div className="text-center p-4 bg-accent-soft rounded-lg">
                  <div className="text-2xl font-bold text-foreground">{(counts.mapped_percent * 100).toFixed(1)}%</div>
                  <div className="text-sm text-muted-foreground">Coverage</div>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {rows.length > 0 && (
          <Card className="bg-surface-elevated">
            <CardHeader>
              <CardTitle>Line Items</CardTitle>
              <CardDescription>
                Showing {((currentPage - 1) * ITEMS_PER_PAGE) + 1} to {Math.min(currentPage * ITEMS_PER_PAGE, rows.length)} of {rows.length} items
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
                    {paginatedRows.map((row, index) => (
                      <TableRow key={index}>
                        <TableCell className="font-medium">{row.line_item}</TableCell>
                        <TableCell>{row.grandparent}</TableCell>
                        <TableCell>{row.parent}</TableCell>
                        <TableCell>
                          <Badge 
                            variant={row.source === "existing" ? "secondary" : "outline"}
                            className={row.source === "existing" ? "bg-success text-success-foreground" : "bg-warning text-warning-foreground"}
                          >
                            {row.source === "existing" ? "Existing" : "Predicted"}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>

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

              <div className="flex flex-col sm:flex-row gap-3 mt-6">
                <Button onClick={handleSave} disabled={saving} variant="default">
                  <Save className="mr-2 h-4 w-4" />
                  {saving ? "Saving..." : "Save "}
                </Button>
                <Button onClick={handleDownloadCSV} variant="outline">
                  <Download className="mr-2 h-4 w-4" />
                  Download CSV
                </Button>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
};

export default Index;