#!/bin/env python
# works in conda scipion3 env
# must source 
# modified from
# defocusgrad (from rdrighetto)
# https://github.com/CellArchLab/cryoet-scripts/blob/main/defocusgrad/defocusgrad

ctffind_exe = '/home/sconnell/local/ctffind/bin/ctffind'

import argparse
import os
import subprocess
import mrcfile
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import pearsonr
from sklearn.linear_model import RANSACRegressor


def main():

    args = get_args()
    # Get unbinned stack dimensions:
    with mrcfile.open(args.st, permissive=True) as mrc:
        stdim = mrc.header["nx"], mrc.header["ny"], mrc.header["nz"]
        apix = mrc.voxel_size.x

    print("\nPixel size of %s is %.3f Å" % (args.st, apix))
    print("If this is wrong, you have to adjust the MRC file header!")
    print(f'Image dimensions (x,y,z): {stdim[0]},{stdim[1]},{stdim[2]}')

    # Get rootname of aligned stack:
    stfilename = os.path.basename(args.st)
    strootname, _ = os.path.splitext(stfilename)   
    
    paramDictLeft = {}
    paramDictLeft['input'] = args.st
    paramDictLeft['output'] = strootname + '_ali_left.mrc'
    paramDictLeft['xform'] = args.xf
    paramDictLeft['offset_x'] = -stdim[0]//4
    paramDictLeft['offset_y'] = 0
    paramDictLeft['bin'] = args.bin
    paramDictLeft['outsize_x'] = stdim[0]//paramDictLeft['bin']//2
    paramDictLeft['outsize_y'] = stdim[1]//paramDictLeft['bin'] 
    paramDictLeft['extraopts'] = args.newst_options
    
    newst_left_com = "newstack -in %(input)s "
    newst_left_com += "-ou %(output)s " 
    newst_left_com += "-xform %(xform)s " 
    newst_left_com += "-offset %(offset_x)d,%(offset_y)d " 
    newst_left_com += "-bin %(bin)d "
    newst_left_com += "-size %(outsize_x)d,%(outsize_y)d "
    newst_left_com += "%(extraopts)s"
    
    print("\nGenerating left-side aligned stack:\n")
    print(newst_left_com % paramDictLeft)
    newst_left_out = subprocess.run([newst_left_com % paramDictLeft], capture_output=True, text=True, shell=True)
    
    paramDictRight = {}
    paramDictRight['input'] = args.st
    paramDictRight['output'] = strootname + '_ali_right.mrc'
    paramDictRight['xform'] = args.xf
    paramDictRight['offset_x'] = +stdim[0]//4
    paramDictRight['offset_y'] = 0
    paramDictRight['bin'] = args.bin
    paramDictRight['outsize_x'] = stdim[0]//paramDictRight['bin']//2
    paramDictRight['outsize_y'] = stdim[1]//paramDictRight['bin'] 
    paramDictRight['extraopts'] = args.newst_options
    
    newst_right_com = "newstack -in %(input)s "
    newst_right_com += "-ou %(output)s " 
    newst_right_com += "-xform %(xform)s " 
    newst_right_com += "-offset %(offset_x)d,%(offset_y)d " 
    newst_right_com += "-bin %(bin)d "
    newst_right_com += "-size %(outsize_x)d,%(outsize_y)d "
    newst_right_com += "%(extraopts)s"
    
    print("\nGenerating right-side aligned stack:\n")
    print(newst_right_com % paramDictRight)
    newst_right_out = subprocess.run([newst_right_com % paramDictRight], capture_output=True, text=True, shell=True)
    
    paramDictCtfFind = {}
    paramDictCtfFind['ismovie'] = "no"
    paramDictCtfFind['apix'] = apix * args.bin
    paramDictCtfFind['kv'] = args.kV
    paramDictCtfFind['cs'] = args.Cs
    paramDictCtfFind['ac'] = args.Ac
    paramDictCtfFind['specbox'] = args.spectrum_boxsize
    paramDictCtfFind['minres'] = args.minres
    paramDictCtfFind['maxres'] = args.maxres
    paramDictCtfFind['mindef'] = args.mindef
    paramDictCtfFind['maxdef'] = args.maxdef
    paramDictCtfFind['stepdef'] = args.stepdef
    paramDictCtfFind['slow'] = args.slow
    paramDictCtfFind['phaseshift'] = args.phaseshift
    
    paramDictCtfFindLeft = paramDictCtfFind.copy()
    paramDictCtfFindLeft['input'] = paramDictLeft['output']
    paramDictCtfFindLeft['diag'] = strootname + '_diagnostic_output_left.mrc'
    
    ctffind_com = """ctffind << eof
    %(input)s
    no
    %(diag)s
    %(apix)f
    %(kv)f
    %(cs)f
    %(ac)f
    %(specbox)d
    %(minres)f
    %(maxres)f
    %(mindef)f
    %(maxdef)f
    %(stepdef)f
    no
    %(slow)s
    no
    %(phaseshift)s
    no
    eof
    """
    
    # Set the OMP_NUM_THREADS environment variable
    env = os.environ.copy()
    env['OMP_NUM_THREADS'] = str(args.threads)
    
    print("\nRunning CTFFIND4 on left-side aligned stack:\n")
    print(ctffind_com % paramDictCtfFindLeft)
    ctffind_left_out = subprocess.run([ctffind_com % paramDictCtfFindLeft], capture_output=True, text=True, shell=True, env=env)
    
    paramDictCtfFindRight = paramDictCtfFind.copy()
    paramDictCtfFindRight['input'] = paramDictRight['output']
    paramDictCtfFindRight['diag'] = strootname + '_diagnostic_output_right.mrc'
    
    print("\nRunning CTFFIND4 on right-side aligned stack:\n")
    print(ctffind_com % paramDictCtfFindRight)
    ctffind_right_out = subprocess.run([ctffind_com % paramDictCtfFindRight], capture_output=True, text=True, shell=True, env=env)
    
    print("\nLet's now analyze the results...")
    tilts = np.loadtxt(args.tlt)
    ctfleft = np.loadtxt(strootname + '_diagnostic_output_left.txt')
    ctfright = np.loadtxt(strootname + '_diagnostic_output_right.txt')
    defleft = 0.5 * ( ctfleft[:,1] + ctfleft[:,2] ) / 10 # Defocus in nm
    defright = 0.5 * ( ctfright[:,1] + ctfright[:,2] ) / 10 # Defocus in nm
    
    args.exclude_positive = -args.exclude_positive if args.exclude_positive > 0 else None
    
    print("\nFull list of tilt angles (%d in total):" % tilts.size)
    print(tilts)
    tilts = tilts[args.exclude_negative:args.exclude_positive]
    defleft = defleft[args.exclude_negative:args.exclude_positive]
    defright = defright[args.exclude_negative:args.exclude_positive]
    
    if args.exclude_negative > 0 or args.exclude_positive is None:
        print("Tilt angles that will be INCLUDED in the analysis (%d in total):" % tilts.size)
        print(tilts)
    
    tilts = tilts.reshape(-1, 1)
    defleft = defleft.reshape(-1, 1)
    defright = defright.reshape(-1, 1)
    
    # # Linear fit using numpy.polyfit
    # coefficients_left = np.polyfit(tilts, defleft, 1)
    # fit_left = np.poly1d(coefficients_left)
    
    # # Linear fit using numpy.polyfit
    # coefficients_right = np.polyfit(tilts, defright, 1)
    # fit_right = np.poly1d(coefficients_right)
    
    # Robust linear fit using RANSAC:
    fit_left = RANSACRegressor()
    fit_left.fit(tilts.reshape(-1, 1), defleft.reshape(-1, 1))
    
    fit_right = RANSACRegressor()
    fit_right.fit(tilts.reshape(-1, 1), defright.reshape(-1, 1))
    
    inliers_left = fit_left.inlier_mask_
    outliers_left = np.logical_not(inliers_left)
    inliers_right = fit_right.inlier_mask_
    outliers_right = np.logical_not(inliers_right)
    
    # print(outliers_left)
    # print(outliers_left.sum())
    if outliers_left.sum() > 0:
        print("\nTilt angles EXCLUDED by robust fitting on the left side (%d in total):" % tilts[outliers_left].size)
        print(tilts[outliers_left])
    if outliers_right.sum() > 0:
        print("Tilt angles EXCLUDED by robust fitting on the right side (%d in total):" % tilts[outliers_right].size)
        print(tilts[outliers_right])
    
    print("""
          
    HOW TO MAKE SENSE OF THIS PLOT:
    
    You should have now an "X" shaped plot. If this is not the case, try adjusting the CTFFIND4 parameters used by the defocusgrad script (type 'defocusgrad --help' to see all options), or inspect your data for possible problems.
    NOTE: not all points may be shown because outliers are automatically excluded by robust fitting with RANSAC.
    
    The LEFT side of the tilt series (blue) should have DECREASING defocus towards positive tilt angles (i.e., a negative slope).
    Conversely, the RIGHT side of the tilt series (orange) should have INCREASING defocus towards positive tilt angles (i.e., a positive slope).
    
    If your data satisfy these conditions, you can import it into RELION-4 with -1 defocus handedness. If you have the opposite trend, you need to use +1 defocus handedness.
    If you are using other software for processing your data, please check the corresponding conventions there.
    """
    )
    
    slope_left = fit_left.estimator_.coef_[0]
    slope_right = fit_right.estimator_.coef_[0]
    
    print("\nSlope for left-side fit: %.3f" % slope_left)
    print("Slope for right-side fit: %.3f" % slope_right)
    print("CONCLUSION:")
    if slope_left < 0 and slope_right > 0:
        print("Import into RELION-4 using -1 tilt handedness.")
        polarity = -1
    elif slope_left > 0 and slope_right < 0:
        print("Import into RELION-4 using +1 tilt handedness.")
        polarity = +1
    else:
        print("Fits for both sides have the same slope sign, results inconclusive!!!")
        polarity = 0
        
    
    corr_left, _ = pearsonr(defleft[inliers_left].squeeze(), fit_left.predict(tilts[inliers_left]).squeeze())
    corr_right, _ = pearsonr(defright[inliers_right].squeeze(), fit_right.predict(tilts[inliers_right]).squeeze())
    print("\nCorrelation coefficient for left-side fit: %.3f" % corr_left)
    print("Correlation coefficient for right-side fit: %.3f\n" % corr_right)
    
    if corr_left <= 0.5 or corr_right <= 0.5:
        print("WARNING! Linear fits are very poor, results are not reliable!!!")
        print("Try re-running with different options or inspecting your data for possible problems.\n")
    
    plt.scatter(tilts[inliers_left], defleft[inliers_left], label="Defocus left-side", color='blue')
    plt.plot(tilts[inliers_left], fit_left.predict(tilts[inliers_left]), label="Linear fit left-side", linestyle='--', color='blue')
    plt.scatter(tilts[inliers_right], defright[inliers_right], label="Defocus right-side", color='orange')
    plt.plot(tilts[inliers_right], fit_right.predict(tilts[inliers_right]), label="Linear fit right-side", linestyle='--', color='orange')
    
    if args.show_outliers:
        if outliers_left.sum() > 0:
            plt.scatter(tilts[outliers_left], defleft[outliers_left], label="Outliers left-side", color='blue', alpha=0.25)
        else:
            print("No outliers were detected on the left side!")
        if outliers_right.sum() > 0:
            plt.scatter(tilts[outliers_right], defright[outliers_right], label="Outliers right-side", color='orange', alpha=0.25)
        else:
            print("No outliers were detected on the right side!")
    
    plt.xlabel("Tilt angle [degrees]")
    plt.ylabel("Defocus [nm]")
    plt.legend()
    plt.title("Defocus vs. tilt angle for %s (%d)" % (args.st, polarity))
    
    figname = strootname + "_defocusgrad" + ext
    plt.savefig(figname)
    print("Plot saved as %s" % figname )
    
    plt.show()
    
    if not args.no_clean:
    
        os.remove(paramDictLeft['output'])
        os.remove(paramDictRight['output'])      
    

def get_args(argv=None):
    parser = argparse.ArgumentParser(description="""                                 
    Calculate and plot defocus handedness for an aligned tilt series using robust fitting.\n
    NOTE: the script expects IMOD and CTFFIND4 to be available in PATH.\n
    """, formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    # Create argument groups
    general_group = parser.add_argument_group('General options')
    newst_group = parser.add_argument_group('IMOD newstack options')
    ctffind_group = parser.add_argument_group('CTFFIND4 options')
    
    newst_group.add_argument("--st", 
                        type=str, 
                        required=True, 
                        help="Path to input unaligned tilt series stack in MRC format, preferably NOT dose-filtered."
                        )
    newst_group.add_argument("--xf", 
                        type=str, 
                        required=True, 
                        help="Path to IMOD .xf file for aligning the tilt series."
                        )
    newst_group.add_argument("--tlt", 
                        type=str, 
                        required=True, 
                        help="Path to .tlt file with tilt angles (one per line as in IMOD format)."
                        )
    newst_group.add_argument("--bin", 
                        type=int,
                        default=1, 
                        required=False, 
                        help="Binning factor for aligned left/right stacks."
                        )
    newst_group.add_argument("--newst_options", 
                        type=str,
                        default="-antialias 5 -linear -taper 1,0 -origin", 
                        required=False, 
                        help="Additional options to IMOD's newstack program."
                        )
    ctffind_group.add_argument("--kV", 
                        type=float,
                        default=300.0, 
                        required=False, 
                        help="Acceleration voltage in kV."
                        )
    ctffind_group.add_argument("--Cs", 
                        type=float,
                        default=2.7, 
                        required=False, 
                        help="Spherical aberration in mm."
                        )
    ctffind_group.add_argument("--Ac", 
                        type=float,
                        default=0.07, 
                        required=False, 
                        help="Amplitude contrast."
                        )
    ctffind_group.add_argument("--spectrum_boxsize", 
                        type=int,
                        default=512, 
                        required=False, 
                        help="Size of amplitude spectrum to compute in pixels."
                        )
    ctffind_group.add_argument("--minres", 
                        type=float,
                        default=30.0, 
                        required=False, 
                        help="Minimum resolution in Å."
                        )
    ctffind_group.add_argument("--maxres", 
                        type=float,
                        default=5.0, 
                        required=False, 
                        help="Maximum resolution in Å."
                        )
    ctffind_group.add_argument("--mindef", 
                        type=float,
                        default=5000.0, 
                        required=False, 
                        help="Minimum defocus in Å."
                        )
    ctffind_group.add_argument("--maxdef", 
                        type=float,
                        default=50000.0, 
                        required=False, 
                        help="Maximum defocus in Å."
                        )
    ctffind_group.add_argument("--stepdef", 
                        type=float,
                        default=100.0, 
                        required=False, 
                        help="Defocus search step in Å."
                        )
    ctffind_group.add_argument("--slow", 
                        type=str,
                        default="no", 
                        required=False, 
                        help="Slower, more exhaustive search?"
                        )
    ctffind_group.add_argument("--phaseshift", 
                        type=str,
                        default="no", 
                        required=False, 
                        help="Find additional phase shift?"
                        )
    ctffind_group.add_argument("--threads", 
                        type=int,
                        default=4, 
                        required=False, 
                        help="Number of threads to run CTFFIND in parallel."
                        )
    general_group.add_argument("--exclude_negative", 
                        type=int,
                        default=0, 
                        required=False, 
                        help="Number of tilts on the negative side of the tilt series to manually exclude from the analysis."
                        )
    general_group.add_argument("--exclude_positive", 
                        type=int,
                        default=0, 
                        required=False, 
                        help="Number of tilts on the positive side of the tilt series to manually exclude from the analysis."
                        )
    general_group.add_argument("--no_clean",
                        action="store_true",
                        required=False,
                        help="Do NOT delete left and right aligned stacks at the end of the run. Useful for inspecting results in more detail."
                        )
    general_group.add_argument("--show_outliers",
                        action="store_true",
                        required=False,
                        help="Show outlier points excluded by robust fitting."
                        )
    
    args = parser.parse_args()
    
    # Print usage information
    if not args.st:
        parser.print_help()
    return parser.parse_args(argv)
        

if __name__ == "__main__":
    main()
