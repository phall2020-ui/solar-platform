"""
Global application state for Solar Portfolio Manager.
Replaces Streamlit's st.session_state with Reflex's rx.State.
"""
import reflex as rx
from typing import Optional, List, Dict, Any
import plotly.graph_objects as go
import pandas as pd
import numpy as np


class AppState(rx.State):
    """Global application state."""
    
    # Enable auto-generated setters (required for Reflex 0.9.0+)
    _state_auto_setters: bool = True
    
    # Navigation
    current_page: str = "Dashboard"
    
    # Settings
    fiscal_year_start: int = 4  # April
    data_source: str = "Both"  # "Both", "Solar Toolkit Only", "Monthly Reporting Only"
    
    # Search
    show_search: bool = False
    search_query: str = ""
    
    # Data availability flags
    toolkit_available: bool = False
    reporting_available: bool = False
    
    # Cached data
    toolkit_plants: List[Dict[str, Any]] = []
    toolkit_stats: Dict[str, Any] = {}
    reporting_tables: List[str] = []
    
    # Data range (for smart date defaults)
    data_min_date: str = ""
    data_max_date: str = ""
    
    # API Scanning
    api_scan_results: List[Dict[str, Any]] = []
    is_scanning: bool = False
    scan_error: str = ""
    
    # Selection for Edit/Details
    selected_plant_alias: str = ""
    
    # Loading states
    is_loading: bool = False
    error_message: str = ""
    
    def on_load(self):
        """Initialize data on app load."""
        self.load_all_data()
    
    def load_all_data(self):
        """Load data from all services."""
        self.is_loading = True
        self.error_message = ""
        
        try:
            # Import services here to avoid circular imports
            from services import toolkit, reporting
            
            # Check toolkit availability
            self.toolkit_available = toolkit.is_available()
            if self.toolkit_available:
                try:
                    plants = toolkit.get_plants()
                    self.toolkit_plants = plants if plants else []
                    stats = toolkit.get_readings_stats()
                    self.toolkit_stats = stats if stats else {}
                except Exception as e:
                    self.error_message = f"Error loading toolkit data: {e}"
                    self.toolkit_plants = []
                    self.toolkit_stats = {}
            
            # Check reporting availability
            self.reporting_available = reporting.is_available()
            if self.reporting_available:
                try:
                    tables = reporting.get_tables()
                    self.reporting_tables = tables if tables else []
                    
                    # Set smart date defaults based on available data
                    self._set_smart_date_defaults()
                except Exception as e:
                    self.error_message = f"Error loading reporting data: {e}"
                    self.reporting_tables = []
                    
        except ImportError as e:
            self.error_message = f"Failed to import services: {e}"
        finally:
            self.is_loading = False
    
    def _set_smart_date_defaults(self):
        """Set sensible date defaults based on available data."""
        from datetime import datetime, timedelta
        
        try:
            from services import reporting
            
            # Try to get date range from data
            df = reporting.get_raw_data()
            if df is not None and len(df) > 0:
                # Find date column
                date_col = next((c for c in df.columns if 'date' in c.lower() or 'month' in c.lower()), None)
                if date_col:
                    import pandas as pd
                    dates = pd.to_datetime(df[date_col], errors='coerce').dropna()
                    if len(dates) > 0:
                        min_date = dates.min()
                        max_date = dates.max()
                        
                        # Store data range
                        self.data_min_date = min_date.strftime("%Y-%m-%d")
                        self.data_max_date = max_date.strftime("%Y-%m-%d")
                        
                        # Set analysis defaults to last 3 months of data
                        end_date = max_date
                        start_date = end_date - timedelta(days=90)
                        if start_date < min_date:
                            start_date = min_date
                        
                        date_str_start = start_date.strftime("%Y-%m-%d")
                        date_str_end = end_date.strftime("%Y-%m-%d")
                        
                        # Set defaults for all analysis pages
                        self.fouling_start_date = date_str_start
                        self.fouling_end_date = date_str_end
                        self.shading_baseline_start = date_str_start
                        self.shading_baseline_end = date_str_end
                        self.shading_compare_start = date_str_start
                        self.shading_compare_end = date_str_end
                        self.thermal_start_date = date_str_start
                        self.thermal_end_date = date_str_end
                        self.poa_import_start_date = date_str_start
                        self.poa_import_end_date = date_str_end
                        self.export_start_date = date_str_start
                        self.export_end_date = date_str_end
                        return
        except Exception:
            pass
        
        # Fallback: use last 30 days
        today = datetime.now()
        default_end = today.strftime("%Y-%m-%d")
        default_start = (today - timedelta(days=30)).strftime("%Y-%m-%d")
        
        self.fouling_start_date = default_start
        self.fouling_end_date = default_end
        self.shading_baseline_start = default_start
        self.shading_baseline_end = default_end
        self.shading_compare_start = default_start
        self.shading_compare_end = default_end
        self.thermal_start_date = default_start
        self.thermal_end_date = default_end
        self.poa_import_start_date = default_start
        self.poa_import_end_date = default_end
        self.export_start_date = default_start
        self.export_end_date = default_end
    
    def set_page(self, page: str):
        """Navigate to a page."""
        self.current_page = page
    
    def toggle_search(self):
        """Toggle global search dialog."""
        self.show_search = not self.show_search
    
    def scan_api_for_plants(self):
        """Scan EMIG API for new sites."""
        self.is_scanning = True
        self.scan_error = ""
        self.api_scan_results = []
        yield
        
        try:
            from services import toolkit
            results = toolkit.discover_plants_from_api()
            
            # Identify which are new
            registered_uids = [p['plant_uid'] for p in self.toolkit_plants if 'plant_uid' in p]
            
            processed_results = []
            for p in results:
                uid = p.get('uid') or p.get('id') or p.get('plantUID')
                if uid not in registered_uids:
                    processed_results.append({
                        "uid": uid,
                        "name": p.get('name') or p.get('plantName') or "Unknown Site",
                        "is_new": True
                    })
            
            self.api_scan_results = processed_results
            if not self.api_scan_results:
                self.error_message = "No new plants found in API."
                
        except Exception as e:
            self.scan_error = f"API Scan Failed: {e}"
        finally:
            self.is_scanning = False

    def register_plant(self, alias: str, uid: str, inv_ids: str, dc_size: float, poa_id: str = ""):
        """Register a new plant in the database."""
        try:
            from services import toolkit
            inverter_list = [x.strip() for x in inv_ids.split(",") if x.strip()]
            
            toolkit.save_plant(
                alias=alias,
                plant_uid=uid,
                inverter_ids=inverter_list,
                dc_size_kw=float(dc_size) if dc_size else 1000.0,
                weather_id=poa_id if poa_id else None
            )
            
            # Refresh data
            self.load_all_data()
            # Clear result from scan list
            self.api_scan_results = [p for p in self.api_scan_results if p['uid'] != uid]
            
        except Exception as e:
            self.error_message = f"Failed to register plant: {e}"

    def handle_register_plant_form(self, form_data: dict):
        """Handle form submission for plant registration."""
        alias = form_data.get("alias", "")
        uid = form_data.get("uid", "")
        inv_ids = form_data.get("inv_ids", "")
        dc_size = form_data.get("dc_size", "1000")
        poa_id = form_data.get("poa_id", "")
        
        self.register_plant(alias, uid, inv_ids, float(dc_size) if dc_size else 1000.0, poa_id)


    def delete_plant(self, alias: str):
        """Remove a plant from the registry."""
        try:
            from services import toolkit
            if toolkit.delete_plant(alias):
                self.load_all_data()
        except Exception as e:
            self.error_message = f"Failed to delete plant: {e}"

    @rx.var
    def registered_plant_aliases(self) -> List[str]:
        """List of aliases for registered plants."""
        return [p['alias'] for p in self.toolkit_plants if 'alias' in p]

    @rx.var
    def total_plants_count(self) -> int:
        """Number of registered plants."""
        return len(self.toolkit_plants)
    
    @rx.var
    def total_dc_capacity_kw(self) -> float:
        """Total DC capacity in kW."""
        return sum(
            p.get('dc_size_kw', 0) 
            for p in self.toolkit_plants 
            if p.get('dc_size_kw')
        )
    
    @rx.var
    def total_capacity_display(self) -> str:
        """Formatted total capacity string."""
        capacity = self.total_dc_capacity_kw
        if capacity > 0:
            if capacity >= 1000:
                return f"{capacity/1000:.1f} MW"
            return f"{capacity:.0f} kW"
        return "N/A"
    
    @rx.var
    def plants_with_location(self) -> int:
        """Number of plants with location data."""
        return sum(
            1 for p in self.toolkit_plants 
            if p.get('latitude') and p.get('longitude')
        )

    # ============== ANALYSIS STATE ==============
    
    # Fouling Analysis
    fouling_plant_alias: str = ""
    fouling_start_date: str = ""
    fouling_end_date: str = ""
    fouling_dc_size: float = 1000.0
    fouling_auto_clean_days: int = 3
    fouling_result: Dict[str, Any] = {}
    fouling_loading: bool = False
    fouling_error: str = ""
    
    def set_fouling_dc_size_str(self, value: str):
        """Set DC size from string input."""
        try:
            self.fouling_dc_size = float(value) if value else 1000.0
        except ValueError:
            self.fouling_dc_size = 1000.0

    
    # Shading Analysis
    shading_plant_alias: str = ""
    shading_baseline_start: str = ""
    shading_baseline_end: str = ""
    shading_compare_start: str = ""
    shading_compare_end: str = ""
    shading_result: Dict[str, Any] = {}
    shading_loading: bool = False
    shading_error: str = ""
    
    # Clipping Analysis
    clipping_plant_alias: str = ""
    clipping_year: int = 2024
    clipping_dc_capacity: float = 100.0
    clipping_ac_capacity: float = 80.0
    clipping_efficiency: float = 0.98
    clipping_result: Dict[str, Any] = {}
    clipping_loading: bool = False
    clipping_error: str = ""
    
    # Thermal Loss Analysis
    thermal_plant_alias: str = ""
    thermal_start_date: str = ""
    thermal_end_date: str = ""
    thermal_temp_coeff: float = -0.4
    thermal_ref_temp: float = 25.0
    thermal_result: Dict[str, Any] = {}
    thermal_loading: bool = False
    thermal_error: str = ""
    
    # String setters for numeric inputs (to avoid lambda issues with Reflex Vars)
    def set_clipping_year_str(self, value: str):
        """Set clipping year from string input."""
        try:
            self.clipping_year = int(value) if value else 2024
        except ValueError:
            self.clipping_year = 2024
    
    def set_clipping_dc_capacity_str(self, value: str):
        """Set clipping DC capacity from string input."""
        try:
            self.clipping_dc_capacity = float(value) if value else 100.0
        except ValueError:
            self.clipping_dc_capacity = 100.0
    
    def set_clipping_ac_capacity_str(self, value: str):
        """Set clipping AC capacity from string input."""
        try:
            self.clipping_ac_capacity = float(value) if value else 80.0
        except ValueError:
            self.clipping_ac_capacity = 80.0
    
    def set_thermal_temp_coeff_str(self, value: str):
        """Set thermal temp coefficient from string input."""
        try:
            self.thermal_temp_coeff = float(value) if value else -0.4
        except ValueError:
            self.thermal_temp_coeff = -0.4
    
    def set_thermal_ref_temp_str(self, value: str):
        """Set thermal reference temp from string input."""
        try:
            self.thermal_ref_temp = float(value) if value else 25.0
        except ValueError:
            self.thermal_ref_temp = 25.0

    def run_fouling_analysis(self):
        """Execute fouling analysis using Solar Toolkit."""
        if not self.fouling_plant_alias:
            self.fouling_error = "Please select a plant"
            return
            
        self.fouling_loading = True
        self.fouling_error = ""
        self.fouling_result = {}
        
        try:
            from services import toolkit
            
            # Get plant UID from alias
            plant = next(
                (p for p in self.toolkit_plants if p['alias'] == self.fouling_plant_alias),
                None
            )
            if not plant:
                self.fouling_error = "Plant not found"
                return
            
            result = toolkit.run_fouling_analysis(
                plant_uid=plant['plant_uid'],
                start_date=self.fouling_start_date.replace("-", ""),
                end_date=self.fouling_end_date.replace("-", ""),
                dc_size_kw=self.fouling_dc_size,
                auto_clean_days=self.fouling_auto_clean_days
            )
            
            # Store result (convert DataFrame to dict if needed)
            self.fouling_result = {
                "fouling_index": result.get("fouling_index", 0),
                "fouling_level": result.get("fouling_level", "Unknown"),
                "data_points": len(result.get("df_result", [])) if result.get("df_result") is not None else 0,
            }
            
        except Exception as e:
            self.fouling_error = f"Analysis failed: {str(e)}"
        finally:
            self.fouling_loading = False

    def run_shading_analysis(self):
        """Execute shading analysis using Solar Toolkit."""
        if not self.shading_plant_alias:
            self.shading_error = "Please select a plant"
            return
            
        self.shading_loading = True
        self.shading_error = ""
        self.shading_result = {}
        
        try:
            from services import toolkit
            
            plant = next(
                (p for p in self.toolkit_plants if p['alias'] == self.shading_plant_alias),
                None
            )
            if not plant:
                self.shading_error = "Plant not found"
                return
            
            # Convert dates to month strings YYYY-MM
            baseline_months = [self.shading_baseline_start[:7], self.shading_baseline_end[:7]]
            compare_months = [self.shading_compare_start[:7], self.shading_compare_end[:7]]
            
            merged_df, summary_df = toolkit.run_shading_analysis(
                plant_uid=plant['plant_uid'],
                baseline_months=baseline_months,
                compare_months=compare_months
            )
            
            self.shading_result = {
                "data_points": len(merged_df) if merged_df is not None else 0,
                "inverters_analyzed": len(summary_df) if summary_df is not None else 0,
            }
            
        except Exception as e:
            self.shading_error = f"Analysis failed: {str(e)}"
        finally:
            self.shading_loading = False

    def run_clipping_analysis(self):
        """Execute clipping analysis using Solar Toolkit."""
        if not self.clipping_plant_alias:
            self.clipping_error = "Please select a plant"
            return
            
        self.clipping_loading = True
        self.clipping_error = ""
        self.clipping_result = {}
        
        try:
            from services import toolkit
            
            result = toolkit.run_clipping_analysis(
                plant_alias=self.clipping_plant_alias,
                start_date=f"{self.clipping_year}-01-01",
                end_date=f"{self.clipping_year}-12-31",
                inverter_specs={
                    "dc_capacity": self.clipping_dc_capacity,
                    "ac_capacity": self.clipping_ac_capacity,
                    "efficiency": self.clipping_efficiency,
                }
            )
            
            self.clipping_result = {
                "metrics": result.get("metrics", {}),
                "has_data": result.get("timeseries") is not None,
            }
            
        except Exception as e:
            self.clipping_error = f"Analysis failed: {str(e)}"
        finally:
            self.clipping_loading = False

    def run_thermal_analysis(self):
        """Execute thermal loss analysis."""
        if not self.thermal_plant_alias:
            self.thermal_error = "Please select a plant"
            return
            
        self.thermal_loading = True
        self.thermal_error = ""
        self.thermal_result = {}
        
        try:
            # Thermal analysis is not yet implemented in toolkit
            # Placeholder for future implementation
            self.thermal_result = {
                "status": "not_implemented",
                "message": "Thermal analysis backend not yet available"
            }
            
        except Exception as e:
            self.thermal_error = f"Analysis failed: {str(e)}"
        finally:
            self.thermal_loading = False

    # ============== POA IMPORT STATE ==============
    
    poa_import_plant_alias: str = ""
    poa_import_start_date: str = ""
    poa_import_end_date: str = ""
    poa_import_loading: bool = False
    poa_import_result: str = ""
    poa_import_error: str = ""
    
    async def handle_poa_upload(self, files: list[rx.UploadFile]):
        """Handle POA file upload and import."""
        if not self.poa_import_plant_alias:
            self.poa_import_error = "Please select a plant first"
            return
            
        self.poa_import_loading = True
        self.poa_import_error = ""
        self.poa_import_result = ""
        
        try:
            from services import toolkit
            import tempfile
            import os
            
            total_imported = 0
            
            for file in files:
                # Save uploaded file to temp directory
                upload_data = await file.read()
                temp_dir = tempfile.mkdtemp()
                temp_path = os.path.join(temp_dir, file.filename)
                
                with open(temp_path, 'wb') as f:
                    f.write(upload_data)
                
                # Import the POA data
                count = toolkit.import_poa_data(
                    plant_alias=self.poa_import_plant_alias,
                    csv_file_path=temp_path,
                    start_date=self.poa_import_start_date or "2020-01-01",
                    end_date=self.poa_import_end_date or "2030-12-31",
                )
                total_imported += count if count else 0
                
                # Clean up temp file
                os.remove(temp_path)
                os.rmdir(temp_dir)
            
            self.poa_import_result = f"Successfully imported {total_imported} records from {len(files)} file(s)"
            
        except Exception as e:
            self.poa_import_error = f"Import failed: {str(e)}"
        finally:
            self.poa_import_loading = False

    # ============== DATA EXPORT STATE ==============
    
    export_data_type: str = "Operational Readings"
    export_plant_filter: str = ""
    export_start_date: str = ""
    export_end_date: str = ""
    export_format: str = "CSV"
    export_loading: bool = False
    export_error: str = ""
    export_result: str = ""
    
    def run_data_export(self):
        """Export data based on configuration."""
        self.export_loading = True
        self.export_error = ""
        self.export_result = ""
        
        try:
            from services import toolkit
            import tempfile
            import os
            
            # Get the data based on type
            if self.export_data_type == "Plant Registry":
                # Export plant list
                data = self.toolkit_plants
                filename = "plant_registry_export"
            else:
                # Export readings (placeholder - would need actual implementation)
                self.export_result = "Export functionality will be available after readings export is implemented in ToolkitBridge"
                return
            
            # TODO: Actually create and download the file
            self.export_result = f"Export prepared: {self.export_data_type} ({len(data)} records)"
            
        except Exception as e:
            self.export_error = f"Export failed: {str(e)}"
        finally:
            self.export_loading = False

    # ============== WATERFALL ANALYSIS STATE ==============
    
    waterfall_loading: bool = False
    waterfall_data_available: bool = False
    waterfall_budget_gen: str = "—"
    waterfall_actual_gen: str = "—"
    waterfall_variance: str = "—"
    waterfall_variance_positive: bool = True
    
    def generate_waterfall(self):
        """Generate waterfall variance analysis."""
        self.waterfall_loading = True
        yield
        
        try:
            # Load data from reporting bridge
            from services.reporting_bridge import reporting
            
            df = reporting.get_raw_data()
            if df is not None and len(df) > 0:
                # Calculate aggregates
                budget_col = next((c for c in df.columns if 'budget' in c.lower() or 'forecast' in c.lower()), None)
                actual_col = next((c for c in df.columns if 'actual' in c.lower() and 'gen' in c.lower()), None)
                
                if budget_col and actual_col:
                    budget = df[budget_col].sum()
                    actual = df[actual_col].sum()
                    variance = ((actual - budget) / budget * 100) if budget > 0 else 0
                    
                    self.waterfall_budget_gen = f"{budget/1000:,.0f}"
                    self.waterfall_actual_gen = f"{actual/1000:,.0f}"
                    self.waterfall_variance = f"{variance:+.1f}"
                    self.waterfall_variance_positive = variance >= 0
                    self.waterfall_data_available = True
                else:
                    self.waterfall_data_available = False
            else:
                self.waterfall_data_available = False
                
        except Exception as e:
            self.error_message = f"Waterfall analysis failed: {e}"
            self.waterfall_data_available = False
        finally:
            self.waterfall_loading = False

    # ============== LOSS WATERFALL STATE ==============
    
    lw_plant_alias: str = ""
    lw_month: str = ""
    lw_budget_gen: float = 0.0
    lw_loading: bool = False
    lw_error: str = ""
    lw_result: Dict[str, Any] = {}
    
    def set_lw_budget_gen_str(self, value: str):
        """Set budget generation from string input."""
        try:
            self.lw_budget_gen = float(value) if value else 0.0
        except ValueError:
            self.lw_budget_gen = 0.0
    
    @rx.var
    def lw_budget_gen_str(self) -> str:
        """Budget generation as string for input binding."""
        return str(self.lw_budget_gen) if self.lw_budget_gen > 0 else ""
    
    @rx.var
    def lw_has_results(self) -> bool:
        """Whether loss waterfall results are available."""
        return bool(self.lw_result) and 'components' in self.lw_result
    
    @rx.var
    def lw_waterfall_fig(self) -> Optional[go.Figure]:
        """Generate Plotly waterfall chart figure."""
        if not self.lw_result or 'waterfall' not in self.lw_result:
            return None
            
        waterfall_data = self.lw_result['waterfall']
        
        fig = go.Figure(go.Waterfall(
            name="Loss Breakdown",
            orientation="v",
            measure=[d['type'] for d in waterfall_data],
            x=[d['name'] for d in waterfall_data],
            textposition="outside",
            text=[f"{abs(d['value']):,.0f}" if d['type'] != 'total' else f"{d['value']:,.0f}" for d in waterfall_data],
            y=[d['value'] for d in waterfall_data],
            connector={"line": {"color": "rgb(63, 63, 63)"}},
            decreasing={"marker": {"color": "#ef4444"}}, # negative color
            increasing={"marker": {"color": "#10b981"}}, # positive color
            totals={"marker": {"color": "#3b82f6"}}      # primary color
        ))

        fig.update_layout(
            title=f"Loss Breakdown: {self.lw_plant_alias}",
            showlegend=False,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font={"color": "#64748b"},
            margin=dict(l=20, r=20, t=60, b=20),
            height=400,
            xaxis=dict(tickangle=-45),
        )
        
        return fig
    
    @rx.var
    def lw_budget_display(self) -> str:
        """Formatted budget generation."""
        if self.lw_budget_gen > 0:
            return f"{self.lw_budget_gen:,.0f}"
        return "—"
    
    @rx.var
    def lw_total_loss_display(self) -> str:
        """Formatted total loss."""
        if self.lw_result and 'total_loss_kwh' in self.lw_result:
            return f"{self.lw_result['total_loss_kwh']:,.0f} kWh"
        return "—"
    
    @rx.var
    def lw_total_loss_pct_display(self) -> str:
        """Formatted total loss percentage."""
        if self.lw_result and 'total_loss_pct' in self.lw_result:
            return f"{self.lw_result['total_loss_pct']:.1f}% of budget"
        return ""
    
    @rx.var
    def lw_actual_display(self) -> str:
        """Formatted estimated actual generation."""
        if self.lw_result and 'actual_gen_kwh' in self.lw_result:
            return f"{self.lw_result['actual_gen_kwh']:,.0f}"
        return "—"
    
    @rx.var
    def lw_clipping_active(self) -> bool:
        comps = self.lw_result.get('components', {})
        return comps.get('clipping', {}).get('active', False)
    
    @rx.var
    def lw_clipping_loss(self) -> str:
        comps = self.lw_result.get('components', {})
        loss = comps.get('clipping', {}).get('loss_kwh', 0)
        return f"{loss:,.0f} kWh" if loss else "0 kWh"
    
    @rx.var
    def lw_curtailment_active(self) -> bool:
        comps = self.lw_result.get('components', {})
        return comps.get('curtailment', {}).get('active', False)
    
    @rx.var
    def lw_curtailment_loss(self) -> str:
        comps = self.lw_result.get('components', {})
        loss = comps.get('curtailment', {}).get('loss_kwh', 0)
        return f"{loss:,.0f} kWh" if loss else "0 kWh"
    
    @rx.var
    def lw_thermal_active(self) -> bool:
        comps = self.lw_result.get('components', {})
        return comps.get('thermal', {}).get('active', False)
    
    @rx.var
    def lw_thermal_loss(self) -> str:
        comps = self.lw_result.get('components', {})
        loss = comps.get('thermal', {}).get('loss_kwh', 0)
        return f"{loss:,.0f} kWh" if loss else "0 kWh"
    
    @rx.var
    def lw_shading_active(self) -> bool:
        comps = self.lw_result.get('components', {})
        return comps.get('shading', {}).get('active', False)
    
    @rx.var
    def lw_shading_loss(self) -> str:
        comps = self.lw_result.get('components', {})
        loss = comps.get('shading', {}).get('loss_kwh', 0)
        return f"{loss:,.0f} kWh" if loss else "0 kWh"
    
    @rx.var
    def lw_fouling_active(self) -> bool:
        comps = self.lw_result.get('components', {})
        return comps.get('fouling', {}).get('active', False)
    
    @rx.var
    def lw_fouling_loss(self) -> str:
        comps = self.lw_result.get('components', {})
        loss = comps.get('fouling', {}).get('loss_kwh', 0)
        return f"{loss:,.0f} kWh" if loss else "0 kWh"
    
    @rx.var
    def lw_availability_active(self) -> bool:
        comps = self.lw_result.get('components', {})
        return comps.get('availability', {}).get('active', False)
    
    @rx.var
    def lw_availability_loss(self) -> str:
        comps = self.lw_result.get('components', {})
        loss = comps.get('availability', {}).get('loss_kwh', 0)
        return f"{loss:,.0f} kWh" if loss else "0 kWh"
    
    def run_loss_waterfall(self):
        """Execute loss waterfall analysis."""
        if not self.lw_plant_alias:
            self.lw_error = "Please select a site"
            return
        
        if not self.lw_month:
            self.lw_error = "Please select a month"
            return
        
        self.lw_loading = True
        self.lw_error = ""
        self.lw_result = {}
        yield
        
        try:
            # Get plant UID from alias
            plant = next(
                (p for p in self.toolkit_plants if p['alias'] == self.lw_plant_alias),
                None
            )
            if not plant:
                self.lw_error = "Plant not found"
                self.lw_loading = False
                return
            
            plant_uid = plant['plant_uid']
            ac_capacity = plant.get('dc_size_kw', 1000)
            
            # Import and run the loss waterfall module
            import sys
            from pathlib import Path
            sys.path.insert(0, str(Path(__file__).parent.parent / "modules"))
            
            from loss_waterfall import compute_loss_waterfall
            
            result = compute_loss_waterfall(
                plant_uid=plant_uid,
                month=self.lw_month,
                ac_capacity_kw=ac_capacity,
                budget_gen_kwh=self.lw_budget_gen if self.lw_budget_gen > 0 else None
            )
            
            if 'error' in result:
                self.lw_error = result['error']
            else:
                self.lw_result = result
            
        except Exception as e:
            self.lw_error = f"Analysis failed: {str(e)}"
        finally:
            self.lw_loading = False

    # ============== EXCOM REPORT STATE ==============

    
    excom_total_generation: str = "—"
    excom_gen_variance: str = "—"
    excom_gen_variance_positive: bool = True
    excom_weighted_pr: str = "—"
    excom_pr_variance: str = "—"
    excom_pr_variance_positive: bool = True
    excom_availability: str = "—"
    excom_avail_status: str = "—"
    excom_avail_ok: bool = True
    excom_plant_count: str = "—"
    excom_total_capacity: str = "—"
    excom_site_data: List[Dict[str, Any]] = []
    excom_top_performers: List[str] = []
    excom_underperformers: List[str] = []
    excom_action_items: List[str] = []
    
    def generate_excom_report(self):
        """Generate executive summary report."""
        try:
            from services.reporting_bridge import reporting
            
            df = reporting.get_raw_data()
            if df is not None and len(df) > 0:
                # Calculate portfolio metrics
                actual_col = next((c for c in df.columns if 'actual' in c.lower() and 'gen' in c.lower()), None)
                budget_col = next((c for c in df.columns if 'budget' in c.lower() or 'forecast' in c.lower()), None)
                pr_col = next((c for c in df.columns if 'pr' in c.lower()), None)
                avail_col = next((c for c in df.columns if 'avail' in c.lower()), None)
                
                if actual_col:
                    total_gen = df[actual_col].sum() / 1000  # MWh
                    self.excom_total_generation = f"{total_gen:,.0f}"
                
                if actual_col and budget_col:
                    actual = df[actual_col].sum()
                    budget = df[budget_col].sum()
                    variance = ((actual - budget) / budget * 100) if budget > 0 else 0
                    self.excom_gen_variance = f"{variance:+.1f}%"
                    self.excom_gen_variance_positive = variance >= 0
                
                if pr_col:
                    avg_pr = df[pr_col].mean()
                    self.excom_weighted_pr = f"{avg_pr:.1f}"
                    self.excom_pr_variance = f"{avg_pr - 79:.1f}%"  # vs 79% target
                    self.excom_pr_variance_positive = avg_pr >= 79
                
                if avail_col:
                    avg_avail = df[avail_col].mean()
                    self.excom_availability = f"{avg_avail:.1f}"
                    self.excom_avail_ok = avg_avail >= 99
                    self.excom_avail_status = "On Target" if avg_avail >= 99 else "Below Target"
                
                # Plant counts from toolkit
                self.excom_plant_count = str(len(self.toolkit_plants))
                self.excom_total_capacity = f"{self.total_dc_capacity_kw / 1000:.1f}"
                
                # Top performers / underperformers (placeholder)
                self.excom_top_performers = ["Site data will appear here"]
                self.excom_underperformers = ["Site data will appear here"]
                self.excom_action_items = ["Review underperforming sites", "Schedule maintenance"]
                
        except Exception as e:
            self.error_message = f"Excom report failed: {e}"
