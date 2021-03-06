/**
 *  Copyright 2007-2008 University Of Southern California
 *
 *  Licensed under the Apache License, Version 2.0 (the "License");
 *  you may not use this file except in compliance with the License.
 *  You may obtain a copy of the License at
 *
 *  http://www.apache.org/licenses/LICENSE-2.0
 *
 *  Unless required by applicable law or agreed to in writing,
 *  software distributed under the License is distributed on an "AS IS" BASIS,
 *  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 *  See the License for the specific language governing permissions and
 *  limitations under the License.
 */

package edu.isi.pegasus.planner.catalog.transformation.classes;

import edu.isi.pegasus.common.util.PegasusURL;
import edu.isi.pegasus.planner.catalog.classes.Profiles;
import edu.isi.pegasus.planner.classes.Profile;
import edu.isi.pegasus.planner.namespace.Pegasus;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * A container data class to use in the Transformation Catalog
 * 
 * @author Karan Vahi
 */
public class Container implements Cloneable {
    
    /**
     * The types of container supported.
     */
    public static enum TYPE{ docker, singularity };
    
    /**
     * Singularity is picky about extensions as it uses that for loading the container image
     */
    protected static  Set<String> mSupportedSingularityExtensions = null;
    
    protected static Set<String> getsupportedSingularityExtensions(){
        if( mSupportedSingularityExtensions == null ){
            //from http://singularity.lbl.gov/user-guide#other-container-formats-supported 
            mSupportedSingularityExtensions = new HashSet<String>();
            mSupportedSingularityExtensions.add( ".img" );
            mSupportedSingularityExtensions.add( ".simg" );
            mSupportedSingularityExtensions.add( ".tar" );
            mSupportedSingularityExtensions.add( ".tar.gz" );
            mSupportedSingularityExtensions.add( ".tar.bz2" );
            mSupportedSingularityExtensions.add( ".cpio" );
            mSupportedSingularityExtensions.add( ".cpio.gz" );
        }
        return mSupportedSingularityExtensions;
    }

    /**
     * the container name assigned by user in the TC
     */
    protected String mName;
    
    /**
     * the LFN used internally for determining destination basenames for staging.
     */
    protected String mLFN;
    
    /**
     * Type of container to use
     */
    protected TYPE mType;
    
    /**
     * URL to image in a docker hub or a url to an existing docker
     * file exported as a tar file
     */
    protected PegasusURL mImageURL; 

     /**
      * optional site attribute to tell pegasus which site tar file
      * exists. useful for handling file URL's correctly
      */ 
    protected String mImageSite;
    
    /**
     * a url to an existing docker file to build container image  from scratch
     */
    protected PegasusURL mDefinitionFileURL;
    
    /**
     * The profiles associated with the site.
     */
    protected Profiles mProfiles;
    
    /**
     * Default constructor
     */
    public Container(){
        mType = TYPE.docker;
        mName     = null;
        mLFN      = null;
        mImageURL = null;
        mDefinitionFileURL = null;
        mImageSite = null;
        mProfiles = new Profiles();
    }
    
    /**
     * Overloaded constructor
     * @param name
     */
    public Container(String name){
        this();
        mName = name;
        setLFN( name );
    }
    
    /**
     * Set the name/identifier for the container
     * 
     * @param name 
     */
    public void setName( String name ){
        mName = name;
        setLFN( name );
    }
    
    /**
     * The name of the container transformation.
     * 
     * @return 
     */
    public String getName(){
        return mName;
    }
    
    /**
     * Set the LFN  for the container
     * 
     * @param name 
     */
    protected final void setLFN( String name ){
       mLFN = name;
    }
    
    /**
     * The name of the project
     * 
     * @return 
     */
    public String getLFN(){
        return mLFN;
    }
    
    /**
     * Compute LFN to be used based on the image URL for the container
     * 
     * @param url
     * 
     * @return LFN 
     */
    public String computeLFN( PegasusURL url ){
        String lfn = this.getName();
        String protocol = url.getProtocol();
        String path = url.getPath();
        if( this.mType.equals( Container.TYPE.singularity) ){
            
            String suffix = null;
            if( protocol.startsWith( PegasusURL.SINGULARITY_PROTOCOL_SCHEME ) ){
                //default suffix while pulling from singularity hub is .simg
                suffix = ".simg";
            }
            else{ 
                //determine the suffix in the URL
                int dotIndex = path.indexOf( '.' );
                if( dotIndex != -1  ){
                    suffix = path.substring(dotIndex);
                    if( !Container.getsupportedSingularityExtensions().contains( suffix ) ){
                        throw new RuntimeException( "Invalid suffix " + suffix + " determined singularity image url " + url );
                    }
                }
                else{
                    throw new RuntimeException( "Unable to compute singularity extension from url " + url );
                }
            }
            lfn = lfn + suffix;
        }
        return lfn;
    }
    
    /**
     * Set the image URL
     * 
     * @param url 
     */
    public void setImageURL( String url ){
        mImageURL = new PegasusURL( url );
        setLFN( computeLFN( mImageURL ) );
    }
    
    /**
     * Return the URL to the image
     * @return 
     */
    public PegasusURL getImageURL(){
        return mImageURL;
    }
    
    /**
     * Set image definition URL
     * 
     * @param url 
     */
    public void setImageDefinitionURL( String url ){
        mDefinitionFileURL = new PegasusURL( url );
    }
    
    /**
     * Return image defintion URL
     * 
     * @return 
     */
    public PegasusURL getImageDefinitionURL(){
        return mDefinitionFileURL;
    }
    
    /**
     * Set the site where image resides
     * 
     * @param site 
     */
    public void setImageSite( String site  ){
        mImageSite = site;
    }
    
    /**
     * Return site with which image is associated
     * 
     * @return 
     */
    public String getImageSite(){
        return mImageSite;
    }
    
    /**
     * Allows you to add one profile at a time to the transformation.
     * @param profiles profiles to be added.
     */
    public void addProfiles( Profiles profiles ) {
    	if(profiles != null) {
    		if ( this.mProfiles == null ) {
    			this.mProfiles = new Profiles();
            }
    		this.mProfiles.addProfilesDirectly( profiles );
    	}
    }


    /**
     * Allows you to add one profile at a time to the transformation.
     * @param profile Profile  A single profile consisting of mNamespace, key and value
     */
    public void addProfile( Profile profile ) {
        if ( profile != null ) {
            if ( this.mProfiles == null ) {
                this.mProfiles = new Profiles();
            }
            //PM-826 allow multiple profiles with same key 
            if( profile.getProfileNamespace().equalsIgnoreCase( Pegasus.NAMESPACE_NAME ) ){
                this.mProfiles.addProfile( profile );
            }
            else{
                this.mProfiles.addProfileDirectly( profile );
            }
        }
    }

    /**
     * Returns the list of profiles associated with the transformation.
     * @return List Returns null if no profiles associated.
     */
    public List<Profile> getProfiles() {
        return ( this.mProfiles == null ) ? null : this.mProfiles.getProfiles();
    }

    /**
     * Returns the profiles for a particular Namespace.
     * @param namespace String The mNamespace of the profile
     * @return List   List of Profile objects. returns null if none are found.
     */
    public List<Profile> getProfiles( String namespace ) {
        return ( this.mProfiles == null ) ? null : mProfiles.getProfiles(namespace);
    }
    
    
    public Profiles getProfilesObject(){
        return this.mProfiles;
    }
    
    /**
     * Allows you to add multiple profiles to the transformation.
     * @param profiles List of Profile objects containing the profile information.
     */
    public void addProfiles( List profiles ) {
        if ( profiles != null ) {
            if ( this.mProfiles == null ) {
                this.mProfiles = new Profiles();
            }
            this.mProfiles.addProfilesDirectly( profiles );
        }
    }

    /**
     * Set the type of the container.
     * 
     * @param type 
     */
    public void setType( TYPE type ){
        this.mType = type;
    }
    
    
    /**
     * Return the type of the container.
     * 
     * @return  type 
     */
    public TYPE getType( ){
        return this.mType;
    }
    
    
    /**
     * Returns the clone of the object.
     *
     * @return the clone
     */
    public Object clone(){
        Container obj;
        try{
            obj = ( Container ) super.clone();
            obj.setType( mType );
            obj.setImageSite(mImageSite);
            obj.setLFN( this.mLFN );
            obj.setName( this.mName);
            
            PegasusURL url = this.getImageDefinitionURL();
            if( url != null ){
                obj.setImageDefinitionURL( url.getURL()  );
            }
            url = this.getImageURL();
            if( url != null ){
                obj.setImageURL( url.getURL()  );
            }
            //FIX me check for profiles clone
            obj.mProfiles = new Profiles();
            obj.addProfiles( this.mProfiles );
            
        }
        catch( CloneNotSupportedException e ){
            //somewhere in the hierarch chain clone is not implemented
            throw new RuntimeException("Clone not implemented in the base class of " + this.getClass().getName(),
                                       e );
        }
        return obj;
    }
    
    /**
     * Returns textual description of object
     * 
     * @return 
     */
    public String toString(){
        StringBuilder sb = new StringBuilder();
        sb.append( "cont ").append(this.getLFN() ).append( "{").append("\n");
        sb.append( "\t" ).append( "type     " ).append( "\t" ).append( this.getType() ).append( "\n");
        if( this.getImageURL() != null ){
            sb.append( "\t" ).append( "image    " ).append( "\t" ).append( this.getImageURL().getURL() ).append( "\n");
        }
        sb.append( "\t" ).append( "image_site " ).append( "\t" ).append( this.getImageSite() ).append( "\n");
        if( this.getImageDefinitionURL() != null ){
            sb.append( "\t" ).append( "dockerfile " ).append( "\t" ).append( this.getImageDefinitionURL().getURL() ).append( "\n");
        }
        for( Profile p: this.getProfiles()){
             sb.append( "\t" ).append( "profile   " ).append("\t").append( p.getProfileNamespace() ).append( "\t" ).
                               append( p.getProfileKey()).append( " " ).append( p.getProfileValue()).append( "\n");
        }
        sb.append( "}").append("\n");
        return sb.toString();
    }
}
